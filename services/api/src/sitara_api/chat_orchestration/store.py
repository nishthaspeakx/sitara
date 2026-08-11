"""Stage 14 — persistence: transcript, Trust Sheet, safety queue (§6.4).

Three writes, three reasons:

* `messages` is the transcript. §34.2: the message embeds the FULL snapshot of
  every fact it cites, not a reference to one. A Trust Sheet opened in two
  years reads that snapshot, never a recomputation.
* `guidance_logs` is the why-payload behind the Trust Sheet (§30.4), carrying
  the same snapshots and the §5.4 confidence the turn was served at.
* `safety_events` is the L1–L5 ladder's record and the human review queue
  (§9, §22.9), written against a PSEUDONYMISED user reference per §6.4.

The six §33.1 audio fields are written on every message, text turns included.
They are the explicit field model that makes voice replay honest; leaving them
off a text message would make "no audio" indistinguishable from "not recorded".

Identifiers are coerced to ObjectId HERE, at the boundary. §6.4 types
`messages.conversation_id`, `guidance_logs.user_id` and `guidance_logs.message_id`
as `objectId` and the collection validators enforce it, while the pipeline
carries §33.2's product identity as a string all the way from the router. One
conversion point beats a string leaking into a validator rejection at write
time — which is precisely what happened before `test_store_mongo.py` existed.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from bson import ObjectId
from bson.errors import InvalidId
from sitara_schemas.facts import ConfidenceState, FactSnapshot

from sitara_api.chat_orchestration.types import (
    SafetyAssessment,
    SafetyLevel,
    Stage,
)
from sitara_api.db.documents import stamp

logger = logging.getLogger(__name__)


class MalformedIdentifier(ValueError):
    """A product identifier that is not a Mongo _id (§33.2)."""


def to_object_id(value: str | ObjectId, *, field_name: str) -> ObjectId:
    """§33.2: Mongo `_id` is the product identity, so every reference is one.

    Raises rather than inventing an id: a turn written under a fabricated
    conversation id would be an orphan in the transcript, which is worse than
    a loud failure.
    """
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(value)
    except (InvalidId, TypeError) as exc:
        raise MalformedIdentifier(f"{field_name} is not a Mongo _id: {value!r}") from exc

#: §33.1: a text turn has no audio, and its playback policy says so.
TEXT_PLAYBACK_POLICY = "text_only"
TRANSCRIPT_STATUS_TEXT = "not_applicable"


@dataclass(frozen=True)
class ReviewEntry:
    """A turn a human must look at (§9 validator double-failure, §22.9 L4).

    `assessment` travels with the entry because §6.4 gives `safety_events` a
    `classifier_scores` field and §12 reads it for pattern analytics — "is this
    the third L3 this month?". A row that recorded only which stage tripped
    would leave that field holding something that is not a score.
    """

    stage: Stage
    reason: str
    trace_id: str
    user_ref: str
    conversation_id: str
    locale: str
    level: SafetyLevel
    created_at: dt.datetime
    assessment: SafetyAssessment | None = None


class MessageStore(Protocol):
    async def save_message(self, document: dict[str, Any]) -> str: ...
    async def save_guidance_log(self, document: dict[str, Any]) -> None: ...
    async def load_message(
        self, conversation_id: str, message_id: str
    ) -> dict[str, Any] | None: ...


class ReviewQueue(Protocol):
    async def enqueue(self, entry: ReviewEntry) -> None: ...


def pseudonymise(user_id: str) -> str:
    """§6.4's `user_ref`: stable enough for pattern analytics, not a user id.

    A safety row must be joinable to itself over time — "is this the third
    L3 this month?" is exactly what §12's pattern analytics asks — without the
    safety collection becoming a second index of who people are.
    """
    return hashlib.sha256(f"safety:{user_id}".encode()).hexdigest()[:32]


def build_message(
    *,
    conversation_id: str | ObjectId,
    role: str,
    content: str,
    locale: str,
    fact_snapshots: Sequence[FactSnapshot] = (),
    safety: SafetyAssessment | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """One `messages` document, §6.4-shaped and §34.2-complete."""
    document: dict[str, Any] = {
        "conversation_id": to_object_id(conversation_id, field_name="conversation_id"),
        "role": role,
        "type": "text",
        "content": content,
        "locale": locale,
        "fact_ids": [snapshot.fact_id for snapshot in fact_snapshots],
        "fact_snapshots": [snapshot.model_dump(mode="json") for snapshot in fact_snapshots],
        "safety_labels": (
            [
                {"risk_class": label.risk_class.value, "score": label.score, "source": label.source}
                for label in safety.labels
            ]
            if safety
            else []
        ),
        # --- the six §33.1 fields, always present ------------------------
        "source_audio_asset_id": None,
        "tts_audio_asset_id": None,
        "transcript_status": TRANSCRIPT_STATUS_TEXT,
        "source_audio_expires_at": None,
        "source_audio_deleted_at": None,
        "playback_policy": TEXT_PLAYBACK_POLICY,
    }
    return stamp(document, now=now)


def build_guidance_log(
    *,
    user_id: str | ObjectId,
    local_date: str,
    message_id: str | ObjectId | None,
    fact_snapshots: Sequence[FactSnapshot],
    confidence: ConfidenceState,
    why: dict[str, Any],
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """The Trust Sheet's audit row (§6.4, §30.4)."""
    document: dict[str, Any] = {
        "user_id": to_object_id(user_id, field_name="user_id"),
        "date": local_date,
        "briefing_id": None,
        "message_id": (
            to_object_id(message_id, field_name="message_id") if message_id else None
        ),
        "fact_ids": [snapshot.fact_id for snapshot in fact_snapshots],
        "fact_snapshots": [snapshot.model_dump(mode="json") for snapshot in fact_snapshots],
        "template_ids": [],
        "confidence": confidence.value,
        "why": why,
    }
    return stamp(document, now=now)


def build_safety_event(entry: ReviewEntry) -> dict[str, Any]:
    """One `safety_events` row (§6.4, §9 ladder, §22.9 queue).

    `classifier_scores` is CSFLE-encrypted under the `safety` key class (§13),
    which is what makes it the right home for the L1 scores AND for the
    trigger detail — a reviewer needs the excerpt that failed, and §13 requires
    that excerpt never sit in the clear.
    """
    payload: dict[str, Any] = {
        "trigger": {"stage": entry.stage.value, "reason": entry.reason},
        "labels": [],
        "classifier_degraded": False,
    }
    if entry.assessment is not None:
        payload["labels"] = [
            {"risk_class": label.risk_class.value, "score": label.score, "source": label.source}
            for label in entry.assessment.labels
        ]
        payload["risk_class"] = entry.assessment.risk_class.value
        payload["classifier_degraded"] = entry.assessment.degraded
    return stamp(
        {
            "user_ref": entry.user_ref,
            "level": entry.level.name,
            "classifier_scores": payload,
            "action": f"queued:{entry.stage.value}",
            "review_status": "pending",
            "trace_id": entry.trace_id,
            "conversation_id": entry.conversation_id,
            "locale": entry.locale,
        },
        now=entry.created_at,
    )


# --------------------------------------------------------------------------
# Mongo implementations
# --------------------------------------------------------------------------


class MongoMessageStore:
    def __init__(self, db: Any) -> None:
        self._db = db

    async def save_message(self, document: dict[str, Any]) -> str:
        result = await self._db.messages.insert_one(document)
        return str(result.inserted_id)

    async def save_guidance_log(self, document: dict[str, Any]) -> None:
        await self._db.guidance_logs.insert_one(document)

    async def load_message(
        self, conversation_id: str, message_id: str
    ) -> dict[str, Any] | None:
        """§25.4's quoted turn, read back for the pipeline.

        Scoped by conversation as well as by id, and that is not belt-and-
        braces: `quoted_message_id` arrives from the client, so an unscoped
        lookup would let any caller quote any message in the database into
        their own prompt and read the reply. The conversation is the boundary
        the user already has.
        """
        try:
            oid = to_object_id(message_id, field_name="messages._id")
            conversation = to_object_id(conversation_id, field_name="messages.conversation_id")
        except MalformedIdentifier:
            return None
        return await self._db.messages.find_one(
            {"_id": oid, "conversation_id": conversation}
        )


class MongoReviewQueue:
    """Writes `safety_events` with `review_status="pending"` (§6.4, §22.9)."""

    def __init__(self, db: Any) -> None:
        self._db = db

    async def enqueue(self, entry: ReviewEntry) -> None:
        await self._db.safety_events.insert_one(build_safety_event(entry))


# --------------------------------------------------------------------------
# In-memory implementations (tests, and a dev run without Mongo)
# --------------------------------------------------------------------------


@dataclass
class InMemoryMessageStore:
    """A fake that behaves like the real collection in the ways that matter.

    It mints a real ObjectId rather than a readable "msg-1": the id it returns
    is fed straight back into `guidance_logs.message_id`, which §6.4 types as
    objectId. A friendlier fake is how the string-vs-ObjectId defect stayed
    invisible for a whole milestone.
    """

    messages: list[dict[str, Any]] = field(default_factory=list)
    guidance_logs: list[dict[str, Any]] = field(default_factory=list)

    async def save_message(self, document: dict[str, Any]) -> str:
        document.setdefault("_id", ObjectId())
        self.messages.append(document)
        return str(document["_id"])

    async def save_guidance_log(self, document: dict[str, Any]) -> None:
        self.guidance_logs.append(document)

    async def load_message(
        self, conversation_id: str, message_id: str
    ) -> dict[str, Any] | None:
        # Scoped by conversation, exactly as the real collection is — a fake
        # that accepts what the real system rejects is a defect in the fake,
        # and here "accepts" would mean handing back another conversation's
        # message to be quoted into a prompt.
        try:
            oid = to_object_id(message_id, field_name="messages._id")
            conversation = to_object_id(conversation_id, field_name="messages.conversation_id")
        except MalformedIdentifier:
            return None
        return next(
            (
                m
                for m in self.messages
                if m.get("_id") == oid and m.get("conversation_id") == conversation
            ),
            None,
        )


@dataclass
class InMemoryReviewQueue:
    entries: list[ReviewEntry] = field(default_factory=list)

    async def enqueue(self, entry: ReviewEntry) -> None:
        self.entries.append(entry)
