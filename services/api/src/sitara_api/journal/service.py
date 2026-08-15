"""The Journal's public face (§30.5, S21–S23).

The timeline is a MERGE, not a table. Four collections already hold what
happened; this assembles them into the calendar+list §30.5 describes, marks
which artefacts the user saved, and never copies a sentence.

Deletion is where the care goes. §30.5 gives three deletions different blast
radii and §44.4 completes the fourth, and they are separate methods here for
the reason the memory module gives for its scoped verbs: a boolean would
invite one to be mistaken for another, and the mistake is invisible until
somebody notices Tara has forgotten something.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Sequence

from bson import ObjectId

from sitara_api.journal.models import (
    ArtefactType,
    JournalDay,
    JournalEntry,
    JournalSave,
)
from sitara_api.journal.search import (
    JournalSearch,
    SearchFilters,
    SearchHit,
    SearchMode,
)
from sitara_api.journal.store import JournalStore

logger = logging.getLogger(__name__)


class JournalService:
    def __init__(
        self,
        *,
        store: JournalStore,
        search: JournalSearch,
        memory_service: object | None = None,
    ) -> None:
        self._store = store
        self._search = search
        #: §30.5's journal-entry deletion offers a checkbox that reaches
        #: `memories`. Optional so the Journal still works where memory is
        #: unavailable — the checkbox is then simply not offered, rather than
        #: offered and silently ineffective.
        self._memory = memory_service

    # -- read ---------------------------------------------------------------

    async def timeline(
        self,
        user_id: ObjectId,
        *,
        since: str | None = None,
        until: str | None = None,
    ) -> list[JournalDay]:
        """§30.5's calendar+list, grouped by the user's LOCAL date.

        Briefs and reflections carry their own local date (§32.13 stores them
        that way), so the grouping is theirs, not this function's. Calls and
        saves carry an instant and are placed by it.
        """
        entries: list[JournalEntry] = []
        entries.extend(await self._store.briefs(user_id, since=since, until=until))
        entries.extend(await self._store.reflections(user_id, since=since, until=until))
        entries.extend(await self._store.calls(user_id))
        entries.extend(await self._store.saved_guidance(user_id))

        entries = [e for e in entries if _within(e.local_date, since, until)]
        entries = await self._mark_saved(user_id, entries)
        entries = await self._render_saved_guidance(entries)
        return _group_by_day(entries)

    async def day(self, user_id: ObjectId, local_date: str) -> JournalDay:
        """S22 — one date. Same assembly, one day wide."""
        days = await self.timeline(user_id, since=local_date, until=local_date)
        return days[0] if days else JournalDay(local_date=local_date, entries=())

    async def search(
        self,
        user_id: ObjectId,
        *,
        query: str,
        filters: SearchFilters | None = None,
        mode: SearchMode = SearchMode.EXPLICIT,
        limit: int = 50,
    ) -> list[SearchHit]:
        return await self._search.run(
            user_id=user_id,
            query=query,
            filters=filters or SearchFilters(),
            mode=mode,
            limit=limit,
        )

    # -- save (§44) ---------------------------------------------------------

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
        return await self._store.save(
            user_id=user_id,
            artefact_type=artefact_type,
            artefact_ref=artefact_ref,
            message_id=message_id,
            note=note,
            now=now,
        )

    async def unsave(self, *, user_id: ObjectId, save_id: ObjectId) -> bool:
        """§44.4: the pointer goes, the artefact stays."""
        return await self._store.unsave(user_id=user_id, save_id=save_id)

    # -- delete (§30.5 / §44.4) --------------------------------------------

    async def delete_artefact(
        self,
        *,
        user_id: ObjectId,
        artefact_type: ArtefactType,
        artefact_ref: str,
        delete_memories: bool = False,
        message_ids: Sequence[ObjectId] = (),
        now: dt.datetime | None = None,
    ) -> dict[str, int]:
        """§30.5: "delete a journal entry → artefact removed (memories sourced
        from it survive unless also deleted — offered as a checkbox)".

        Three things happen, in an order that matters: the artefact goes, its
        saves go with it (§44.4 — a pointer at a deleted artefact is a dead
        row), and the checkbox is honoured LAST. Doing the memory work first
        would withdraw consent for a deletion that might then fail.

        `delete_memories` is passed through untouched rather than defaulted
        true anywhere along the way: §30.5 makes keeping them the default, and
        a default that drifts is a user losing memories she chose to keep.
        """
        removed = await self._delete_artefact_row(user_id, artefact_type, artefact_ref)
        saves_removed = await self._store.delete_saves_for_artefact(
            user_id=user_id, artefact_type=artefact_type, artefact_ref=artefact_ref
        )

        memories_deleted = 0
        if delete_memories and message_ids and self._memory is not None:
            memories_deleted = await self._memory.on_journal_entry_deleted(  # type: ignore[attr-defined]
                user_id=user_id,
                message_ids=list(message_ids),
                delete_memories=True,
                now=now,
            )
        elif delete_memories and self._memory is None:  # pragma: no cover - wiring guard
            logger.error(
                "journal-entry deletion asked to delete memories with no memory "
                "service wired — the checkbox was offered and could not be honoured"
            )

        return {
            "artefacts": removed,
            "saves": saves_removed,
            "memories": memories_deleted,
        }

    async def _delete_artefact_row(
        self, user_id: ObjectId, artefact_type: ArtefactType, artefact_ref: str
    ) -> int:
        """Remove the artefact from wherever it actually lives.

        Guidance is the exception and deliberately so: §30.5 puts talk in the
        thread, so "removing" saved guidance from the Journal removes the
        SAVE, not the turn. Deleting the turn is §27's chat deletion, a
        different act with a different confirm.
        """
        db = self._store._db  # noqa: SLF001 - the store owns the handle; this is its module
        if artefact_type is ArtefactType.BRIEF:
            result = await db.daily_briefings.delete_one(
                {"user_id": user_id, "date": artefact_ref}
            )
            return int(result.deleted_count)
        if artefact_type is ArtefactType.REFLECTION:
            result = await db.night_reflections.delete_one(
                {"user_id": user_id, "date": artefact_ref}
            )
            return int(result.deleted_count)
        if artefact_type is ArtefactType.CALL:
            result = await db.call_sessions.update_one(
                {"user_id": user_id, "_id": ObjectId(artefact_ref)},
                {"$set": {"summary": None, "updated_at": dt.datetime.now(dt.UTC)}},
            )
            # The session row is metering and state (§25.7); the SUMMARY is the
            # journal artefact, and it is the summary the user is deleting.
            return int(result.modified_count)
        return 0

    # -- assembly helpers ---------------------------------------------------

    async def _mark_saved(
        self, user_id: ObjectId, entries: list[JournalEntry]
    ) -> list[JournalEntry]:
        saves = await self._store.saves_by_ref(user_id)
        if not saves:
            return entries
        out: list[JournalEntry] = []
        for entry in entries:
            save = saves.get((entry.artefact_type.value, entry.ref))
            if save is None or entry.saved:
                out.append(entry)
                continue
            out.append(
                JournalEntry(
                    artefact_type=entry.artefact_type,
                    ref=entry.ref,
                    local_date=entry.local_date,
                    occurred_at=entry.occurred_at,
                    title=entry.title,
                    preview=entry.preview,
                    message_id=entry.message_id,
                    conversation_id=entry.conversation_id,
                    saved=True,
                    save_id=str(save.save_id),
                    note=save.note,
                    confidence=entry.confidence,
                )
            )
        return out

    async def _render_saved_guidance(self, entries: list[JournalEntry]) -> list[JournalEntry]:
        """Fetch the saved turns' text from where it lives (§44.2).

        The Journal holds no copy, so a saved bubble is displayed by going and
        reading the message. A turn that is gone — §27's chat rules removed it
        — renders as an absence rather than as nothing: the save is a record
        that she kept something, and silently dropping the row would erase
        that too.
        """
        wanted = [
            ObjectId(e.message_id)
            for e in entries
            if e.artefact_type is ArtefactType.GUIDANCE and e.message_id
        ]
        if not wanted:
            return entries
        messages = await self._store.messages_by_id(wanted)

        out: list[JournalEntry] = []
        for entry in entries:
            if entry.artefact_type is not ArtefactType.GUIDANCE or not entry.message_id:
                out.append(entry)
                continue
            doc = messages.get(ObjectId(entry.message_id))
            content = doc.get("content") if doc else None
            out.append(
                JournalEntry(
                    artefact_type=entry.artefact_type,
                    ref=entry.ref,
                    local_date=entry.local_date,
                    occurred_at=entry.occurred_at,
                    title=entry.title,
                    preview=content if isinstance(content, str) else None,
                    message_id=entry.message_id,
                    conversation_id=(
                        str(doc["conversation_id"])
                        if doc and doc.get("conversation_id")
                        else entry.conversation_id
                    ),
                    saved=True,
                    save_id=entry.save_id,
                    note=entry.note,
                    confidence=entry.confidence,
                )
            )
        return out


def _within(local_date: str, since: str | None, until: str | None) -> bool:
    if since and local_date < since:
        return False
    return not (until and local_date > until)


def _group_by_day(entries: Sequence[JournalEntry]) -> list[JournalDay]:
    """Newest day first; within a day, newest artefact first.

    Entries with no resolvable date are dropped rather than bucketed under the
    empty string — an artefact that cannot say when it happened has no place
    on a timeline, and a phantom "" day at the top of the Journal is worse
    than its absence.
    """
    buckets: dict[str, list[JournalEntry]] = {}
    for entry in entries:
        if not entry.local_date:
            logger.debug("journal entry with no local date dropped: %s", entry.ref)
            continue
        buckets.setdefault(entry.local_date, []).append(entry)

    days: list[JournalDay] = []
    for local_date in sorted(buckets, reverse=True):
        same_day = sorted(
            buckets[local_date],
            key=lambda e: (e.occurred_at or dt.datetime.min.replace(tzinfo=dt.UTC)),
            reverse=True,
        )
        days.append(JournalDay(local_date=local_date, entries=tuple(same_day)))
    return days


__all__ = ["JournalService"]
