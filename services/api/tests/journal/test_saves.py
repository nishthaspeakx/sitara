"""`journal_saves` — the pointer, and what deleting one does (CC-011 §44).

§44.2 makes a save a POINTER at an artefact that lives elsewhere. That is not
a storage preference; it is what keeps §30.5's deletion scopes true. A save
that copied the guidance text would leave the copy behind when the source was
deleted, so "delete a journal entry → artefact removed" would silently stop
being true for exactly the guidance a user cared enough to keep.

These tests hold that line from both ends: the row never carries the content,
and the deletions do what §44.4 says they do.
"""

from __future__ import annotations

import pytest
from bson import ObjectId

from sitara_api.journal.models import ArtefactType, NotSaveable
from sitara_api.journal.store import JournalStore
from tests.journal.conftest import NOW, OTHER_USER_ID, USER_ID

pytestmark = pytest.mark.asyncio


async def test_a_save_is_a_pointer_and_carries_no_copy_of_the_guidance(
    store: JournalStore, db
) -> None:
    """§44.2's operative word. The row names WHERE the guidance is."""
    message_id = ObjectId()

    save = await store.save(
        user_id=USER_ID,
        artefact_type=ArtefactType.GUIDANCE,
        artefact_ref=str(message_id),
        message_id=message_id,
        now=NOW,
    )

    doc = await db.journal_saves.find_one({"_id": save.save_id})
    assert doc is not None
    assert doc["artefact_ref"] == str(message_id)
    assert doc["message_id"] == message_id
    # There is no field that could hold the sentence. Not empty — absent.
    assert "content" not in doc
    assert "text" not in doc
    assert doc.get("note") is None


async def test_saving_the_same_artefact_twice_saves_it_once(store: JournalStore) -> None:
    """A double-tap on "save to journal" is one save, enforced by the unique
    index rather than by the client remembering."""
    ref = "2026-08-15"

    first = await store.save(
        user_id=USER_ID, artefact_type=ArtefactType.BRIEF, artefact_ref=ref, now=NOW
    )
    second = await store.save(
        user_id=USER_ID, artefact_type=ArtefactType.BRIEF, artefact_ref=ref, now=NOW
    )

    assert second.save_id == first.save_id
    assert len(await store.list_saves(USER_ID)) == 1


async def test_the_same_ref_under_a_different_type_is_a_different_save(
    store: JournalStore,
) -> None:
    """A brief and a reflection share a local date as their ref. The unique
    index spans (user, type, ref) for exactly that reason — keying on the ref
    alone would make saving a reflection silently overwrite the brief."""
    ref = "2026-08-15"

    await store.save(user_id=USER_ID, artefact_type=ArtefactType.BRIEF, artefact_ref=ref, now=NOW)
    await store.save(
        user_id=USER_ID, artefact_type=ArtefactType.REFLECTION, artefact_ref=ref, now=NOW
    )

    assert len(await store.list_saves(USER_ID)) == 2


async def test_two_users_may_save_the_same_artefact(store: JournalStore, db) -> None:
    ref = "2026-08-15"
    await store.save(user_id=USER_ID, artefact_type=ArtefactType.BRIEF, artefact_ref=ref, now=NOW)
    await store.save(
        user_id=OTHER_USER_ID, artefact_type=ArtefactType.BRIEF, artefact_ref=ref, now=NOW
    )

    assert len(await store.list_saves(USER_ID)) == 1
    assert len(await store.list_saves(OTHER_USER_ID)) == 1


async def test_a_note_is_stored_but_is_the_users_prose_not_the_artefacts(
    store: JournalStore, db
) -> None:
    save = await store.save(
        user_id=USER_ID,
        artefact_type=ArtefactType.CALL,
        artefact_ref=str(ObjectId()),
        note="read this again before the meeting",
        now=NOW,
    )

    doc = await db.journal_saves.find_one({"_id": save.save_id})
    assert doc["note"] == "read this again before the meeting"


# --- §44.4 deletion --------------------------------------------------------


async def test_unsaving_removes_the_pointer_and_nothing_else(
    store: JournalStore, db
) -> None:
    """§44.4: "removes the pointer and nothing else"."""
    message_id = ObjectId()
    await db.messages.insert_one(
        {
            "_id": message_id,
            "conversation_id": ObjectId(),
            "role": "assistant",
            "type": "text",
            "content": "Today the Moon moves through your 10th house.",
            "locale": "en",
            "transcript_status": "none",
            "playback_policy": "none",
            "created_at": NOW,
            "updated_at": NOW,
            "schema_v": 1,
        }
    )
    save = await store.save(
        user_id=USER_ID,
        artefact_type=ArtefactType.GUIDANCE,
        artefact_ref=str(message_id),
        message_id=message_id,
        now=NOW,
    )

    assert await store.unsave(user_id=USER_ID, save_id=save.save_id) is True

    assert await store.list_saves(USER_ID) == []
    assert await db.messages.count_documents({"_id": message_id}) == 1, (
        "unsaving must not reach the turn the guidance lives on"
    )


async def test_deleting_the_artefact_takes_its_saves_with_it(store: JournalStore) -> None:
    """§44.4: "a pointer to a deleted artefact is a dead row, not a record of
    anything"."""
    await store.save(
        user_id=USER_ID, artefact_type=ArtefactType.BRIEF, artefact_ref="2026-08-15", now=NOW
    )
    await store.save(
        user_id=USER_ID, artefact_type=ArtefactType.BRIEF, artefact_ref="2026-08-14", now=NOW
    )

    removed = await store.delete_saves_for_artefact(
        user_id=USER_ID, artefact_type=ArtefactType.BRIEF, artefact_ref="2026-08-15"
    )

    assert removed == 1
    assert [s.artefact_ref for s in await store.list_saves(USER_ID)] == ["2026-08-14"]


async def test_one_users_unsave_cannot_reach_anothers(store: JournalStore) -> None:
    mine = await store.save(
        user_id=USER_ID, artefact_type=ArtefactType.BRIEF, artefact_ref="2026-08-15", now=NOW
    )

    assert await store.unsave(user_id=OTHER_USER_ID, save_id=mine.save_id) is False
    assert len(await store.list_saves(USER_ID)) == 1


async def test_saves_are_listed_newest_first(store: JournalStore) -> None:
    import datetime as dt

    older = await store.save(
        user_id=USER_ID,
        artefact_type=ArtefactType.BRIEF,
        artefact_ref="2026-08-13",
        now=NOW - dt.timedelta(days=2),
    )
    newer = await store.save(
        user_id=USER_ID, artefact_type=ArtefactType.BRIEF, artefact_ref="2026-08-15", now=NOW
    )

    assert [s.save_id for s in await store.list_saves(USER_ID)] == [
        newer.save_id,
        older.save_id,
    ]


async def test_a_milestone_cannot_be_saved(store: JournalStore) -> None:
    """§44.2 permits four artefact types in `journal_saves`; `MILESTONE` is the
    fifth §30.5 type and is DERIVED — a first reading or a birthday has no
    artefact to point at, so a save of one would point at nothing.

    The closed set is enforced in Python, at the store boundary, which is how
    every other closed set in §6.4 is enforced (`messages.role`,
    `messages.playback_policy`): the collection validators declare bson types,
    not enumerations. A save with a type nobody declared cannot be constructed
    here, and this is the test that says so.
    """
    with pytest.raises(NotSaveable):
        await store.save(
            user_id=USER_ID,
            artefact_type=ArtefactType.MILESTONE,
            artefact_ref="first_reading",
            now=NOW,
        )

    assert await store.list_saves(USER_ID) == []
