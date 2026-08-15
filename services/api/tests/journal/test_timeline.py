"""The timeline is a MERGE of four collections (§30.5), and it copies nothing.

The tests worth having here are the ones about *assembly*: that all four
artefact kinds arrive, that they land on the day the user had rather than the
day the server had, that a saved turn is rendered from where it lives, and
that the entry deletion does what its confirm sheet will promise.
"""

from __future__ import annotations

import datetime as dt

import pytest
from bson import ObjectId

from sitara_api.journal.models import ArtefactType
from sitara_api.journal.search import ExactTextSearch
from sitara_api.journal.service import JournalService
from sitara_api.journal.store import JournalStore
from tests.journal.conftest import NOW, USER_ID

pytestmark = pytest.mark.asyncio


@pytest.fixture()
def service(store: JournalStore, db) -> JournalService:  # noqa: ANN001
    return JournalService(store=store, search=ExactTextSearch(db))


async def _brief(db, *, date: str, text: str = "a settled start") -> None:
    await db.daily_briefings.insert_one(
        {
            "_id": ObjectId(),
            "user_id": USER_ID,
            "date": date,
            "locale": "en",
            "modules": [{"module": "core_theme", "text": text}],
            "fact_ids": [],
            "status": "ready",
            "idempotency_key": f"{USER_ID}:{date}:en",
            "confidence": "high_confidence",
            "created_at": NOW,
            "updated_at": NOW,
            "schema_v": 1,
        }
    )


async def _reflection(db, *, date: str, text: str = "a quiet evening") -> None:
    await db.night_reflections.insert_one(
        {
            "_id": ObjectId(),
            "user_id": USER_ID,
            "date": date,
            "entries": [text],
            "memory_chips": [],
            "locale": "en",
            "created_at": NOW,
            "updated_at": NOW,
            "schema_v": 1,
        }
    )


async def _call(
    db, *, ended: dt.datetime, summary: str = "we talked the lease through"
) -> ObjectId:
    doc = {
        "_id": ObjectId(),
        "user_id": USER_ID,
        "conversation_id": ObjectId(),
        "state": "ended",
        "started_at": ended - dt.timedelta(minutes=8),
        "ended_at": ended,
        "summary": summary,
        "created_at": ended,
        "updated_at": ended,
        "schema_v": 1,
    }
    await db.call_sessions.insert_one(doc)
    return doc["_id"]


async def _guidance_message(db, *, content: str) -> ObjectId:
    doc = {
        "_id": ObjectId(),
        "conversation_id": ObjectId(),
        "role": "assistant",
        "type": "text",
        "content": content,
        "locale": "en",
        "fact_ids": [],
        "safety_labels": [],
        "transcript_status": "none",
        "playback_policy": "none",
        "created_at": NOW,
        "updated_at": NOW,
        "schema_v": 1,
    }
    await db.messages.insert_one(doc)
    return doc["_id"]


# --- assembly --------------------------------------------------------------


async def test_all_four_artefact_kinds_reach_the_timeline(
    service: JournalService, store: JournalStore, db
) -> None:
    """§30.5 lists five; the fifth (milestones) is derived and has no store."""
    await _brief(db, date="2026-08-15")
    await _reflection(db, date="2026-08-15")
    await _call(db, ended=NOW)
    message_id = await _guidance_message(db, content="the lease can wait until Thursday")
    await store.save(
        user_id=USER_ID,
        artefact_type=ArtefactType.GUIDANCE,
        artefact_ref=str(message_id),
        message_id=message_id,
        now=NOW,
    )

    days = await service.timeline(USER_ID)

    kinds = {e.artefact_type for day in days for e in day.entries}
    assert kinds == {
        ArtefactType.BRIEF,
        ArtefactType.REFLECTION,
        ArtefactType.CALL,
        ArtefactType.GUIDANCE,
    }


async def test_days_are_newest_first(service: JournalService, db) -> None:
    await _brief(db, date="2026-08-10")
    await _brief(db, date="2026-08-15")
    await _brief(db, date="2026-08-12")

    days = await service.timeline(USER_ID)

    assert [d.local_date for d in days] == ["2026-08-15", "2026-08-12", "2026-08-10"]


async def test_a_brief_lands_on_its_own_local_date_not_the_servers(
    service: JournalService, db
) -> None:
    """§32.13 stores the user's LOCAL date on the brief, so the Journal groups
    by the day she had. A timeline that re-derived the day from a UTC
    timestamp would move every brief for anyone east of London."""
    await _brief(db, date="2026-08-15")

    days = await service.timeline(USER_ID)

    assert days[0].local_date == "2026-08-15"
    assert days[0].entries[0].ref == "2026-08-15"


async def test_a_saved_turn_is_rendered_from_the_thread_not_from_a_copy(
    service: JournalService, store: JournalStore, db
) -> None:
    """§44.2's pointer, from the reading side."""
    sentence = "Today the Moon moves through your 10th house."
    message_id = await _guidance_message(db, content=sentence)
    await store.save(
        user_id=USER_ID,
        artefact_type=ArtefactType.GUIDANCE,
        artefact_ref=str(message_id),
        message_id=message_id,
        now=NOW,
    )

    days = await service.timeline(USER_ID)
    entry = days[0].entries[0]

    assert entry.preview == sentence
    assert entry.saved is True
    # Proof it was a read and not a copy: change the source, re-read.
    await db.messages.update_one({"_id": message_id}, {"$set": {"content": "corrected text"}})
    days = await service.timeline(USER_ID)
    assert days[0].entries[0].preview == "corrected text"


async def test_a_saved_turn_whose_message_is_gone_still_appears(
    service: JournalService, store: JournalStore, db
) -> None:
    """§27's chat rules may remove the turn. The save is a record that she
    kept something — dropping the row silently would erase that too."""
    message_id = await _guidance_message(db, content="something she wanted to keep")
    await store.save(
        user_id=USER_ID,
        artefact_type=ArtefactType.GUIDANCE,
        artefact_ref=str(message_id),
        message_id=message_id,
        now=NOW,
    )
    await db.messages.delete_one({"_id": message_id})

    days = await service.timeline(USER_ID)
    entry = days[0].entries[0]

    assert entry.saved is True
    assert entry.preview is None, "an absence, rendered honestly by the caller"


async def test_an_unsaved_brief_is_marked_unsaved_and_a_saved_one_saved(
    service: JournalService, store: JournalStore, db
) -> None:
    await _brief(db, date="2026-08-15")
    await _brief(db, date="2026-08-14")
    await store.save(
        user_id=USER_ID, artefact_type=ArtefactType.BRIEF, artefact_ref="2026-08-15", now=NOW
    )

    days = {d.local_date: d for d in await service.timeline(USER_ID)}

    assert days["2026-08-15"].entries[0].saved is True
    assert days["2026-08-14"].entries[0].saved is False


async def test_the_day_view_is_one_date_wide(service: JournalService, db) -> None:
    await _brief(db, date="2026-08-15")
    await _brief(db, date="2026-08-14")

    day = await service.day(USER_ID, "2026-08-15")

    assert day.local_date == "2026-08-15"
    assert [e.ref for e in day.entries] == ["2026-08-15"]


async def test_an_empty_day_is_a_day_not_an_error(service: JournalService) -> None:
    """§24.6: no dead ends. A date with nothing on it renders an empty state."""
    day = await service.day(USER_ID, "2026-01-01")

    assert day.local_date == "2026-01-01"
    assert day.entries == ()


# --- deletion (§30.5 / §44.4) ----------------------------------------------


async def test_deleting_a_reflection_removes_it_and_its_save(
    service: JournalService, store: JournalStore, db
) -> None:
    await _reflection(db, date="2026-08-15")
    await store.save(
        user_id=USER_ID,
        artefact_type=ArtefactType.REFLECTION,
        artefact_ref="2026-08-15",
        now=NOW,
    )

    result = await service.delete_artefact(
        user_id=USER_ID, artefact_type=ArtefactType.REFLECTION, artefact_ref="2026-08-15"
    )

    assert result == {"artefacts": 1, "saves": 1, "memories": 0}
    assert await db.night_reflections.count_documents({"user_id": USER_ID}) == 0
    assert await store.list_saves(USER_ID) == []


async def test_deleting_an_artefact_leaves_the_others_alone(
    service: JournalService, db
) -> None:
    await _brief(db, date="2026-08-15")
    await _reflection(db, date="2026-08-15")

    await service.delete_artefact(
        user_id=USER_ID, artefact_type=ArtefactType.BRIEF, artefact_ref="2026-08-15"
    )

    day = await service.day(USER_ID, "2026-08-15")
    assert [e.artefact_type for e in day.entries] == [ArtefactType.REFLECTION]


async def test_deleting_a_call_summary_keeps_the_session_row(
    service: JournalService, db
) -> None:
    """§25.7's `call_sessions` row is metering and state; the SUMMARY is the
    journal artefact. Deleting what she sees must not delete the minutes she
    was billed for."""
    call_id = await _call(db, ended=NOW)

    await service.delete_artefact(
        user_id=USER_ID, artefact_type=ArtefactType.CALL, artefact_ref=str(call_id)
    )

    row = await db.call_sessions.find_one({"_id": call_id})
    assert row is not None, "the session row survives"
    assert row["summary"] is None, "the artefact does not"


async def test_the_checkbox_reaches_memories_only_when_ticked(db) -> None:
    """§30.5's checkbox, wired end to end rather than asserted at each half.

    The two halves are tested separately — `tests/memory/test_deletion_paths.py`
    owns the blast radius — so what this adds is the WIRING: that ticking the
    box on a journal entry actually reaches `memories`, and that leaving it
    unticked reaches nothing. A checkbox offered and silently ineffective is
    the failure this catches.
    """
    from sitara_api.memory.embeddings import DeterministicEmbedder
    from sitara_api.memory.retrieval import ExactVectorSearch
    from sitara_api.memory.service import MemoryService
    from sitara_api.memory.store import MemoryStore
    from sitara_api.memory.taxonomy import MemoryType
    from tests.memory.conftest import consent_for

    memory_store = MemoryStore(db)
    memory_service = MemoryService(
        store=memory_store,
        search=ExactVectorSearch(memory_store),
        embedder=DeterministicEmbedder(),
    )
    journal_store = JournalStore(db)
    service = JournalService(
        store=journal_store, search=ExactTextSearch(db), memory_service=memory_service
    )

    message_id = await _guidance_message(db, content="about the lease")
    memory = await memory_store.create(
        user_id=USER_ID,
        memory_type=MemoryType.DECISION_CONTEXT,
        content="weighing whether to renew the lease",
        consent=consent_for(MemoryType.DECISION_CONTEXT),
        embedding=None,
        source_message_id=message_id,
        now=NOW,
    )
    await _reflection(db, date="2026-08-15")

    unticked = await service.delete_artefact(
        user_id=USER_ID,
        artefact_type=ArtefactType.REFLECTION,
        artefact_ref="2026-08-15",
        delete_memories=False,
        message_ids=[message_id],
    )
    assert unticked["memories"] == 0
    assert await memory_store.get(USER_ID, memory.memory_id) is not None

    await _reflection(db, date="2026-08-16")
    ticked = await service.delete_artefact(
        user_id=USER_ID,
        artefact_type=ArtefactType.REFLECTION,
        artefact_ref="2026-08-16",
        delete_memories=True,
        message_ids=[message_id],
    )
    assert ticked["memories"] == 1
    assert await memory_store.get(USER_ID, memory.memory_id) is None
    # And the withdrawal reached the permanent ledger (CC-011 §44.5).
    assert await db.consents.count_documents({"user_id": USER_ID}) == 1


async def test_unsaving_guidance_does_not_delete_the_turn(
    service: JournalService, store: JournalStore, db
) -> None:
    """§30.5 puts talk in the thread. Removing saved guidance from the Journal
    removes the SAVE — deleting the turn is §27's chat deletion, a different
    act with a different confirm sheet."""
    message_id = await _guidance_message(db, content="the lease can wait")
    save = await store.save(
        user_id=USER_ID,
        artefact_type=ArtefactType.GUIDANCE,
        artefact_ref=str(message_id),
        message_id=message_id,
        now=NOW,
    )

    assert await service.unsave(user_id=USER_ID, save_id=save.save_id) is True

    assert await db.messages.count_documents({"_id": message_id}) == 1
    assert await service.timeline(USER_ID) == []
