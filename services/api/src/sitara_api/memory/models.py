"""The stored shapes (§6.4 `memories`, §32.4 consent, §30.5 deletion).

§6.4 fixes the document: `user_id, type, content, embedding, consent,
visibility, source_message_id, decay_score`. These models are that row, typed,
plus the two records the spec attaches to it — the consent stamp a vault entry
must be able to show, and the source link §30.5's scoped deletion acts on.

Nothing here invents a field. `visibility` and `consent` are the two `object`
cells §6.4 already provides, and everything the module needs to remember about
a memory lives inside one of them.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from bson import ObjectId

from sitara_api.memory.taxonomy import (
    RECONFIRM_WORDING,
    MemoryType,
    age_days,
    decay_score,
)


class ConsentAction(StrEnum):
    """The consent ledger is visible in-app (§13 user rights)."""

    GRANTED = "granted"
    RECONFIRMED = "reconfirmed"
    EDITED = "edited"
    WITHDRAWN = "withdrawn"


class SourceState(StrEnum):
    """§30.5: deleting a conversation marks dependent memory sources
    "source removed" — the memory survives, its provenance does not."""

    PRESENT = "present"
    REMOVED = "removed"


@dataclass(frozen=True)
class ConsentEvent:
    action: ConsentAction
    at: dt.datetime
    #: The exact wording the user agreed to. §32.4 re-confirms wording for
    #: types 7–9, which is only meaningful if the agreed wording is kept.
    wording: str | None = None

    def to_doc(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "at": self.at,
            "wording": self.wording,
        }


@dataclass(frozen=True)
class ConsentRecord:
    """§32.4: "all types explicit-chip". No chip, no memory — there is
    deliberately no code path that stores one without this record."""

    granted: bool
    granted_at: dt.datetime
    #: True when §32.4 required the wording be re-confirmed (types 7–9) AND
    #: the user confirmed it. A type 7–9 memory with this False is refused.
    wording_reconfirmed: bool = False
    history: tuple[ConsentEvent, ...] = ()

    def to_doc(self) -> dict[str, Any]:
        return {
            "granted": self.granted,
            "granted_at": self.granted_at,
            "wording_reconfirmed": self.wording_reconfirmed,
            "history": [event.to_doc() for event in self.history],
        }

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> ConsentRecord:
        return cls(
            granted=bool(doc.get("granted")),
            granted_at=_aware(doc.get("granted_at")) or dt.datetime.now(dt.UTC),
            wording_reconfirmed=bool(doc.get("wording_reconfirmed")),
            history=tuple(
                ConsentEvent(
                    action=ConsentAction(event["action"]),
                    at=_aware(event["at"]) or dt.datetime.now(dt.UTC),
                    wording=event.get("wording"),
                )
                for event in doc.get("history", [])
            ),
        )


@dataclass(frozen=True)
class Visibility:
    """§6.4's `visibility` cell — the per-memory half of §32.4's gates.

    The type-level gates are policy and live in `taxonomy`; what belongs on the
    document is what the USER decided about this one memory: whether she has
    muted it from retrieval, and whether its source still exists (§30.5).
    """

    muted: bool = False
    source_state: SourceState = SourceState.PRESENT

    def to_doc(self) -> dict[str, Any]:
        return {"muted": self.muted, "source_state": self.source_state.value}

    @classmethod
    def from_doc(cls, doc: dict[str, Any] | None) -> Visibility:
        doc = doc or {}
        return cls(
            muted=bool(doc.get("muted")),
            source_state=SourceState(doc.get("source_state", SourceState.PRESENT.value)),
        )


@dataclass(frozen=True)
class Memory:
    """One `memories` row (§6.4), as the rest of the service sees it."""

    memory_id: ObjectId
    user_id: ObjectId
    type: MemoryType
    content: str
    consent: ConsentRecord
    visibility: Visibility = field(default_factory=Visibility)
    source_message_id: ObjectId | None = None
    decay_score: float = 1.0
    created_at: dt.datetime | None = None
    updated_at: dt.datetime | None = None
    #: Never returned to a client and never logged — it is derived data
    #: (§32.5) and 1024 floats of it.
    has_embedding: bool = False

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> Memory:
        return cls(
            memory_id=doc["_id"],
            user_id=doc["user_id"],
            type=MemoryType(doc["type"]),
            content=doc.get("content") or "",
            consent=ConsentRecord.from_doc(doc.get("consent") or {}),
            visibility=Visibility.from_doc(doc.get("visibility")),
            source_message_id=doc.get("source_message_id"),
            decay_score=float(doc.get("decay_score", 1.0)),
            created_at=_aware(doc.get("created_at")),
            updated_at=_aware(doc.get("updated_at")),
            has_embedding=doc.get("embedding") is not None,
        )


def _aware(value: dt.datetime | None) -> dt.datetime | None:
    """BSON stores UTC; a client without `tz_aware` hands back naive values.

    `make_mongo` sets tz_aware, which is the real fix — this keeps the model
    correct for any caller that built its own client, since mixing the two
    kinds raises TypeError in the middle of decay arithmetic.
    """
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=dt.UTC)


def recomputed_decay(memory: Memory, now: dt.datetime) -> float:
    """Decay from the clock, not from the stored value.

    The stored `decay_score` is what the nightly consolidation last wrote
    (§32.4); retrieval must not wait for that job to be right about a memory
    that has aged since. `updated_at` is the reinforcement stamp — a memory the
    user edited or re-confirmed is young again.
    """
    since = memory.updated_at or memory.created_at
    if since is None:
        return memory.decay_score
    return decay_score(memory.type, age_days=age_days(since, now))


@dataclass(frozen=True)
class MemoryCandidate:
    """A suggestion awaiting the user's chip. Not a memory until accepted."""

    type: MemoryType
    content: str
    source_message_id: ObjectId | None = None

    @property
    def requires_reconfirmation(self) -> bool:
        return self.type in RECONFIRM_WORDING


@dataclass(frozen=True)
class Retrieved:
    """A memory that survived search, decay and the §32.4 gates."""

    memory: Memory
    similarity: float
    score: float

    @property
    def memory_id(self) -> str:
        return str(self.memory.memory_id)


class ConsentRequired(ValueError):
    """§32.4: explicit chip, and re-confirmed wording for types 7–9."""


class MedicalContentDeclined(ValueError):
    """§32.4: symptoms and diagnoses "are declined at classification"."""
