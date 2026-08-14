"""Journal types (§30.5, CC-011 §44).

§30.5's rule governs the whole module: **"Journal is what happened; the Vault
is what Tara knows; the thread is where talk lives."** Everything here is on
the first side of that sentence — artefacts of things that occurred, addressed
by when they occurred.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from bson import ObjectId


class ArtefactType(StrEnum):
    """§30.5's five Journal artefact types.

    The first four are the ones a user can SAVE (§44.2); `MILESTONE` is derived
    from dates the system already holds — a first reading, a birthday — and has
    nothing to point at, which is why `journal_saves` never carries one.
    """

    BRIEF = "brief"
    REFLECTION = "reflection"
    CALL = "call"
    GUIDANCE = "guidance"
    MILESTONE = "milestone"


#: The four §44.2 permits in `journal_saves.artefact_type`. A milestone is not
#: a thing that was saved; it is a thing that happened.
SAVEABLE: frozenset[ArtefactType] = frozenset(
    {
        ArtefactType.BRIEF,
        ArtefactType.REFLECTION,
        ArtefactType.CALL,
        ArtefactType.GUIDANCE,
    }
)


class NotSaveable(ValueError):
    """A milestone has no artefact to point at (§44.2)."""


@dataclass(frozen=True)
class JournalSave:
    """One `journal_saves` row — a POINTER, never a copy (§44.2).

    There is deliberately no `content` field. A save that carried the guidance
    text would survive the deletion of the artefact it came from, which would
    make §30.5's "delete a journal entry → artefact removed" false for exactly
    the guidance a user cared enough to keep.
    """

    save_id: ObjectId
    user_id: ObjectId
    artefact_type: ArtefactType
    artefact_ref: str
    saved_at: dt.datetime
    message_id: ObjectId | None = None
    note: str | None = None

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> JournalSave:
        return cls(
            save_id=doc["_id"],
            user_id=doc["user_id"],
            artefact_type=ArtefactType(doc["artefact_type"]),
            artefact_ref=doc["artefact_ref"],
            saved_at=doc["saved_at"],
            message_id=doc.get("message_id"),
            note=doc.get("note"),
        )


@dataclass(frozen=True)
class JournalEntry:
    """One artefact on the timeline.

    `ref` is how the artefact is addressed in its own collection — a local date
    for briefs and reflections, an `_id` for calls and guidance. `title` and
    `preview` are rendered by the caller from the artefact's own store; they
    are not stored here, because the Journal holds no copies.
    """

    artefact_type: ArtefactType
    ref: str
    #: The user's LOCAL calendar date (§32.13's rule, never UTC) — the Journal
    #: is grouped by the day the user had, not the day the server had.
    local_date: str
    occurred_at: dt.datetime | None = None
    title: str | None = None
    preview: str | None = None
    #: §30.5's cross-link: "a journal call-summary links to its thread position".
    message_id: str | None = None
    conversation_id: str | None = None
    saved: bool = False
    save_id: str | None = None
    note: str | None = None
    #: §5.4's state where the artefact carries one. Never invented.
    confidence: str | None = None


@dataclass(frozen=True)
class JournalDay:
    """One local date's artefacts, newest artefact first within the day."""

    local_date: str
    entries: tuple[JournalEntry, ...] = field(default_factory=tuple)


__all__ = [
    "SAVEABLE",
    "ArtefactType",
    "JournalDay",
    "JournalEntry",
    "JournalSave",
    "NotSaveable",
]
