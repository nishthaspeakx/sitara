"""`journal_saves` (CC-011 §44) and the reads the timeline is assembled from.

**The Journal is a VIEW, not a collection.** §30.5 names five artefact types
and four of them already live somewhere: briefs in `daily_briefings`,
reflections in `night_reflections`, call summaries in `call_sessions` (§25.7's
index is cited "per-user call history for the journal"), and milestones are
derived from dates the system already holds. Only the fifth — a save — needed
storage, and §44.2 makes even that a pointer.

So this store writes one collection and reads four. It never copies an
artefact, because a copy would outlive its original and make §30.5's deletion
scopes false.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Sequence
from typing import Any

from bson import ObjectId
from pymongo import DESCENDING
from pymongo.errors import DuplicateKeyError

from sitara_api.db.documents import stamp
from sitara_api.journal.models import (
    SAVEABLE,
    ArtefactType,
    JournalEntry,
    JournalSave,
    NotSaveable,
)

logger = logging.getLogger(__name__)

#: One page of the timeline. The Journal is a calendar+list (§30.5), not an
#: infinite feed, and a year view is P1 polish.
DEFAULT_LIMIT = 100


class JournalStore:
    def __init__(self, db: Any) -> None:
        self._db = db

    # -- saves (§44) --------------------------------------------------------

    async def save(
        self,
        *,
        user_id: ObjectId,
        artefact_type: ArtefactType,
        artefact_ref: str,
        message_id: ObjectId | None = None,
        note: str | None = None,
        now: dt.datetime | None = None,
    ) -> JournalSave:
        """Save an artefact to the Journal. Idempotent per (user, type, ref).

        A double-tap on §25.4's long-press menu is one save, and the unique
        index is what makes that true rather than the client remembering.
        """
        if artefact_type not in SAVEABLE:
            raise NotSaveable(
                f"{artefact_type} is derived, not an artefact — there is nothing "
                "for a save to point at (§44.2)"
            )

        moment = now or dt.datetime.now(dt.UTC)
        document = stamp(
            {
                "user_id": user_id,
                "artefact_type": artefact_type.value,
                "artefact_ref": artefact_ref,
                "message_id": message_id,
                "saved_at": moment,
                "note": note,
            },
            now=moment,
        )
        try:
            result = await self._db.journal_saves.insert_one(document)
        except DuplicateKeyError:
            existing = await self._db.journal_saves.find_one(
                {
                    "user_id": user_id,
                    "artefact_type": artefact_type.value,
                    "artefact_ref": artefact_ref,
                }
            )
            if existing is None:  # pragma: no cover - the index just said it exists
                raise
            return JournalSave.from_doc(existing)
        document["_id"] = result.inserted_id
        return JournalSave.from_doc(document)

    async def list_saves(
        self, user_id: ObjectId, *, limit: int = DEFAULT_LIMIT
    ) -> list[JournalSave]:
        cursor = (
            self._db.journal_saves.find({"user_id": user_id})
            .sort("saved_at", DESCENDING)
            .limit(limit)
        )
        return [JournalSave.from_doc(doc) async for doc in cursor]

    async def saves_by_ref(self, user_id: ObjectId) -> dict[tuple[str, str], JournalSave]:
        """Every save keyed by (type, ref), for marking timeline entries saved.

        One read rather than one per entry: the timeline already knows which
        artefacts it holds, and the saved flag is a join, not a lookup loop.
        """
        return {
            (s.artefact_type.value, s.artefact_ref): s for s in await self.list_saves(user_id)
        }

    async def unsave(self, *, user_id: ObjectId, save_id: ObjectId) -> bool:
        """§44.4: removes the pointer and nothing else."""
        result = await self._db.journal_saves.delete_one({"_id": save_id, "user_id": user_id})
        return result.deleted_count == 1

    async def delete_saves_for_artefact(
        self, *, user_id: ObjectId, artefact_type: ArtefactType, artefact_ref: str
    ) -> int:
        """§44.4: "a pointer to a deleted artefact is a dead row".

        Called when the artefact itself is deleted, never on its own.
        """
        result = await self._db.journal_saves.delete_many(
            {
                "user_id": user_id,
                "artefact_type": artefact_type.value,
                "artefact_ref": artefact_ref,
            }
        )
        return int(result.deleted_count)

    # -- the four artefact reads -------------------------------------------

    async def briefs(
        self, user_id: ObjectId, *, since: str | None = None, until: str | None = None
    ) -> list[JournalEntry]:
        """§30.5: "daily briefs (archived after their day)".

        The date is already the user's LOCAL date (§32.13 stores it that way),
        which is why nothing here touches a timezone: the Journal groups by the
        day the user had, and the brief was generated for exactly that day.
        """
        query = _date_query(user_id, since, until)
        cursor = self._db.daily_briefings.find(query).sort("date", DESCENDING)
        return [
            JournalEntry(
                artefact_type=ArtefactType.BRIEF,
                ref=doc["date"],
                local_date=doc["date"],
                occurred_at=doc.get("generated_at") or doc.get("created_at"),
                confidence=doc.get("confidence"),
            )
            async for doc in cursor
        ]

    async def reflections(
        self, user_id: ObjectId, *, since: str | None = None, until: str | None = None
    ) -> list[JournalEntry]:
        query = _date_query(user_id, since, until)
        cursor = self._db.night_reflections.find(query).sort("date", DESCENDING)
        return [
            JournalEntry(
                artefact_type=ArtefactType.REFLECTION,
                ref=doc["date"],
                local_date=doc["date"],
                occurred_at=doc.get("created_at"),
            )
            async for doc in cursor
        ]

    async def calls(self, user_id: ObjectId, *, limit: int = DEFAULT_LIMIT) -> list[JournalEntry]:
        """§30.5's call summaries, cross-linked to their thread position.

        Only ENDED calls with a summary appear: a call still ringing is not
        something that happened yet, and §25.3's summary chip is what puts one
        here.
        """
        cursor = (
            self._db.call_sessions.find(
                {"user_id": user_id, "summary": {"$ne": None}, "ended_at": {"$ne": None}}
            )
            .sort("started_at", DESCENDING)
            .limit(limit)
        )
        entries: list[JournalEntry] = []
        async for doc in cursor:
            ended = doc.get("ended_at")
            entries.append(
                JournalEntry(
                    artefact_type=ArtefactType.CALL,
                    ref=str(doc["_id"]),
                    local_date=_local_date_of(ended),
                    occurred_at=ended,
                    conversation_id=(
                        str(doc["conversation_id"]) if doc.get("conversation_id") else None
                    ),
                )
            )
        return entries

    async def saved_guidance(self, user_id: ObjectId) -> list[JournalEntry]:
        """The saves that point at a turn (§44.2).

        Guidance reaches the Journal ONLY by being saved — §30.5 lists "saved
        guidance", not "all guidance". The thread is where talk lives.
        """
        entries: list[JournalEntry] = []
        for save in await self.list_saves(user_id):
            if save.artefact_type is not ArtefactType.GUIDANCE:
                continue
            entries.append(
                JournalEntry(
                    artefact_type=ArtefactType.GUIDANCE,
                    ref=save.artefact_ref,
                    local_date=_local_date_of(save.saved_at),
                    occurred_at=save.saved_at,
                    message_id=str(save.message_id) if save.message_id else None,
                    saved=True,
                    save_id=str(save.save_id),
                    note=save.note,
                )
            )
        return entries

    async def messages_by_id(
        self, message_ids: Sequence[ObjectId]
    ) -> dict[ObjectId, dict[str, Any]]:
        """Render material for saved guidance, read from where it lives.

        The Journal holds no copy of a sentence (§44.2), so displaying a saved
        turn means going and getting it. A missing message is not an error —
        §27's chat rules may have removed it — and the caller renders the
        absence honestly.
        """
        if not message_ids:
            return {}
        cursor = self._db.messages.find({"_id": {"$in": list(message_ids)}})
        return {doc["_id"]: doc async for doc in cursor}


def _date_query(user_id: ObjectId, since: str | None, until: str | None) -> dict[str, Any]:
    query: dict[str, Any] = {"user_id": user_id}
    if since or until:
        bounds: dict[str, str] = {}
        if since:
            bounds["$gte"] = since
        if until:
            bounds["$lte"] = until
        query["date"] = bounds
    return query


def _local_date_of(moment: dt.datetime | None) -> str:
    """The artefact's own day, as an ISO date.

    Calls and saves are stamped with an instant rather than a local date, so
    this is the one place the two are reconciled. It is UTC-based and that is a
    known approximation for artefacts that have no stored local date of their
    own — the brief and the reflection, which are the surfaces §32.13's rule
    actually governs, carry theirs and never come through here.
    """
    if moment is None:
        return ""
    return moment.astimezone(dt.UTC).date().isoformat()


__all__ = ["DEFAULT_LIMIT", "JournalStore"]
