"""The night reflection (§10-17, §24.4 S19, §28.2's night variant).

Two rules carry the module:

**One per user-local calendar date, bound at creation** (§27's night-reflection
row: "Reflection binds to user-local calendar day at creation; one per local
date; travel merges gracefully"). §6.4 already gives `night_reflections` a
unique `(user_id, date)` index, so the rule is enforced by the database rather
than by a check that can be raced. Travel merging falls out of binding at
creation: a reflection started in Delhi and finished after landing in London
keeps the date it was started on, because the date was decided once.

**No streaks, no guilt** (§10-17). Enforced by absence — no streak field, no
completion count, no comparison to any other night, and no "you missed
yesterday" anywhere. `missed dates` is not a concept this module can express.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Mapping, Sequence
from typing import Any

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from sitara_api.db.documents import stamp
from sitara_api.reflection.models import Mood, Prompt, Reflection, ReflectionEntry

logger = logging.getLogger(__name__)

#: §10-17: "≤3 min". A soft ceiling on how much one answer may carry — long
#: enough for a real thought, short enough that the ceremony stays a ceremony.
MAX_ENTRY_CHARS = 2000


class ReflectionService:
    def __init__(self, db: Any) -> None:
        self._db = db

    async def get(self, user_id: ObjectId, date: str) -> Reflection | None:
        doc = await self._db.night_reflections.find_one({"user_id": user_id, "date": date})
        return Reflection.from_doc(doc) if doc else None

    async def save(
        self,
        *,
        user_id: ObjectId,
        date: str,
        locale: str,
        entries: Mapping[Prompt, str] | Sequence[ReflectionEntry] = (),
        mood: Mood | None = None,
        memory_chips: Sequence[str] = (),
        now: dt.datetime | None = None,
    ) -> Reflection:
        """Create or update tonight's reflection.

        An upsert rather than create-then-edit: §24.6 forbids dead ends, and a
        user who closes the sheet after one prompt and returns after brushing
        her teeth is continuing, not starting a second reflection. The unique
        `(user_id, date)` index makes that structurally true even under two
        taps racing on a slow connection — the `DuplicateKeyError` branch is
        the losing tap, and it re-reads rather than erroring.
        """
        moment = now or dt.datetime.now(dt.UTC)
        normalised = _entries_of(entries)

        update = {
            "$set": {
                "locale": locale,
                "entries": [
                    {"prompt": e.prompt.value, "text": e.text[:MAX_ENTRY_CHARS]}
                    for e in normalised
                ],
                "mood": mood.value if mood else None,
                "memory_chips": list(memory_chips),
                "updated_at": moment,
            },
            "$setOnInsert": {
                "user_id": user_id,
                # Bound HERE and never recomputed (§27). The caller resolved the
                # user's local date; a service that re-derived it on each write
                # would move a reflection across the date line mid-ceremony.
                "date": date,
                "created_at": moment,
                "schema_v": stamp({}, now=moment)["schema_v"],
            },
        }
        try:
            doc = await self._db.night_reflections.find_one_and_update(
                {"user_id": user_id, "date": date},
                update,
                upsert=True,
                return_document=True,
            )
        except DuplicateKeyError:  # pragma: no cover - the racing second tap
            doc = await self._db.night_reflections.find_one(
                {"user_id": user_id, "date": date}
            )
        if doc is None:  # pragma: no cover - upsert returned nothing and no row exists
            raise RuntimeError("reflection upsert produced no document")
        return Reflection.from_doc(doc)

    async def recent(self, user_id: ObjectId, *, limit: int = 30) -> list[Reflection]:
        """The reflections she has written, newest first.

        Deliberately not "the last 30 days with gaps filled in": a list of
        blank nights is a guilt surface, and §10-17 forbids one. The Journal
        shows what happened, and a night she did not write is a night that did
        not happen here.
        """
        cursor = (
            self._db.night_reflections.find({"user_id": user_id})
            .sort("date", -1)
            .limit(limit)
        )
        return [Reflection.from_doc(doc) async for doc in cursor]


def _entries_of(
    entries: Mapping[Prompt, str] | Sequence[ReflectionEntry],
) -> list[ReflectionEntry]:
    if isinstance(entries, Mapping):
        return [
            ReflectionEntry(prompt=prompt, text=text)
            for prompt, text in entries.items()
            if text and text.strip()
        ]
    return [e for e in entries if e.text and e.text.strip()]


__all__ = ["MAX_ENTRY_CHARS", "ReflectionService"]
