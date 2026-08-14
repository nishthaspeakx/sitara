"""§30.5's deletion scopes, one test per blast radius.

§30.5 gives three deletions genuinely different consequences and §32.15 adds a
fourth. They are easy to confuse and expensive to confuse: each one is a
promise made to a user at a confirm step, and the failure mode is silent — a
conversation delete that also removed memories would look like a working
delete, and nobody would find out until somebody noticed Tara had forgotten
her daughter's name.

So every test here asserts what SURVIVES as hard as what dies. The negatives
are the point:

  · a conversation delete must NOT delete memories
  · an unticked journal checkbox must NOT touch them
  · a memory delete must NOT disturb the journal text that mentions it
  · the withdrawal ledger row must NOT contain what the memory said

Written against the real compose mongo, never a fake, for the reason
`conftest.py` gives: the §6.4 validators are part of what is under test.
"""

from __future__ import annotations

import datetime as dt

import pytest
from bson import ObjectId

from sitara_api.memory.models import SourceState
from sitara_api.memory.service import MemoryService
from sitara_api.memory.store import MemoryStore
from sitara_api.memory.taxonomy import MemoryType
from tests.memory.conftest import NOW, USER_ID, consent_for

pytestmark = pytest.mark.asyncio


async def _memory(
    store: MemoryStore,
    *,
    memory_type: MemoryType = MemoryType.PERSON,
    content: str = "her daughter Ananya sits her boards in March",
    source_message_id: ObjectId | None = None,
):
    return await store.create(
        user_id=USER_ID,
        memory_type=memory_type,
        content=content,
        consent=consent_for(memory_type),
        embedding=None,
        source_message_id=source_message_id,
        now=NOW,
    )


async def _ledger_rows(db, user_id: ObjectId = USER_ID) -> list[dict]:
    return [doc async for doc in db.consents.find({"user_id": user_id})]


# --- 1. delete a memory ----------------------------------------------------


async def test_deleting_a_memory_removes_the_row_and_its_embedding(
    service: MemoryService, store: MemoryStore, db
) -> None:
    memory = await _memory(store)

    assert await service.forget(user_id=USER_ID, memory_id=memory.memory_id) is True

    assert await store.get(USER_ID, memory.memory_id) is None
    assert await db.memories.count_documents({"_id": memory.memory_id}) == 0
    # Not "the API stops returning it" — the document is gone (diagram 8).
    assert [m.memory_id for m in await store.list_vault(USER_ID)] == []


async def test_deleting_a_memory_writes_a_withdrawal_the_user_can_point_at(
    service: MemoryService, store: MemoryStore, db
) -> None:
    """The user's ask: "prove it's gone".

    §30.5's delete is a hard delete and the memory's consent history lives
    INSIDE the deleted document, so withdrawing consent used to destroy the
    only evidence that consent was ever withdrawn. §13 requires a consent
    ledger visible in-app; `consents` is permanent and legal (§6.4). CC-011
    §44.5 joins the two.
    """
    memory = await _memory(store, memory_type=MemoryType.GOAL_INTENTION)

    await service.forget(user_id=USER_ID, memory_id=memory.memory_id)

    rows = await _ledger_rows(db)
    assert len(rows) == 1, "a withdrawal must reach the permanent ledger"
    row = rows[0]
    assert row["type"] == f"memory.{MemoryType.GOAL_INTENTION.value}"
    assert row["revoked_at"] is not None
    assert row["granted_at"] is not None, (
        "the ledger keeps the legal-basis history, not just the end of it"
    )
    assert row["surface"] == "S25"


async def test_the_withdrawal_row_never_carries_what_the_memory_said(
    service: MemoryService, store: MemoryStore, db
) -> None:
    """A tombstone that quotes the memory is a record of what she deleted.

    §32.15 already settled the shape: "the attestation consent record is
    retained (legal basis history), the data is not".
    """
    secret = "she is thinking about leaving her job at the bank"
    memory = await _memory(store, memory_type=MemoryType.WORK_FINANCE, content=secret)

    await service.forget(user_id=USER_ID, memory_id=memory.memory_id)

    row = (await _ledger_rows(db))[0]
    flattened = repr(row)
    assert secret not in flattened
    assert "bank" not in flattened
    assert str(memory.memory_id) not in flattened, (
        "even the id is a handle on the deleted row — the ledger records the "
        "TYPE and the timestamps, nothing that identifies the content"
    )


async def test_each_withdrawal_appends_rather_than_overwriting(
    service: MemoryService, store: MemoryStore, db
) -> None:
    """Onboarding upserts on (user_id, type) because consenting twice to the
    same thing is one consent. Withdrawing two memories of the same type is
    two withdrawals, and §6.4's user_id+type index is deliberately not unique.
    """
    first = await _memory(store, memory_type=MemoryType.PREFERENCE, content="drinks filter coffee")
    second = await _memory(store, memory_type=MemoryType.PREFERENCE, content="walks after dinner")

    await service.forget(user_id=USER_ID, memory_id=first.memory_id)
    await service.forget(user_id=USER_ID, memory_id=second.memory_id)

    rows = await _ledger_rows(db)
    assert len(rows) == 2
    assert {r["type"] for r in rows} == {f"memory.{MemoryType.PREFERENCE.value}"}


async def test_a_failed_delete_writes_no_withdrawal(
    service: MemoryService, db
) -> None:
    """Nothing was withdrawn, so the permanent ledger says nothing."""
    assert await service.forget(user_id=USER_ID, memory_id=ObjectId()) is False
    assert await _ledger_rows(db) == []


async def test_one_users_delete_cannot_reach_anothers_memory(
    service: MemoryService, store: MemoryStore, db
) -> None:
    from tests.memory.conftest import OTHER_USER_ID

    mine = await _memory(store)

    assert await service.forget(user_id=OTHER_USER_ID, memory_id=mine.memory_id) is False
    assert await store.get(USER_ID, mine.memory_id) is not None
    assert await _ledger_rows(db, OTHER_USER_ID) == []


# --- 2. delete a journal entry ---------------------------------------------


async def test_journal_delete_with_the_box_unticked_touches_no_memory(
    service: MemoryService, store: MemoryStore, db
) -> None:
    """§30.5: "memories sourced from it survive unless also deleted — offered
    as a checkbox". Unticked is the DEFAULT, and the default must be inert."""
    message_id = ObjectId()
    memory = await _memory(store, source_message_id=message_id)

    deleted = await service.on_journal_entry_deleted(
        user_id=USER_ID, message_ids=[message_id], delete_memories=False
    )

    assert deleted == 0
    survivor = await store.get(USER_ID, memory.memory_id)
    assert survivor is not None
    assert survivor.visibility.source_state is SourceState.PRESENT, (
        "an unticked journal delete is not a conversation delete — the source "
        "turn still exists, so the provenance is untouched"
    )
    assert await _ledger_rows(db) == [], "nothing was withdrawn"


async def test_journal_delete_with_the_box_ticked_withdraws_each_memory(
    service: MemoryService, store: MemoryStore, db
) -> None:
    message_id = ObjectId()
    doomed = await _memory(store, source_message_id=message_id)
    unrelated = await _memory(store, content="her mother's name is Sudha")

    deleted = await service.on_journal_entry_deleted(
        user_id=USER_ID, message_ids=[message_id], delete_memories=True
    )

    assert deleted == 1
    assert await store.get(USER_ID, doomed.memory_id) is None
    assert await store.get(USER_ID, unrelated.memory_id) is not None, (
        "the checkbox scopes to memories sourced from THIS entry"
    )
    rows = await _ledger_rows(db)
    assert len(rows) == 1, "one withdrawal per memory actually withdrawn"


# --- 3. delete a conversation ----------------------------------------------


async def test_conversation_delete_keeps_every_memory_and_marks_the_source(
    service: MemoryService, store: MemoryStore, db
) -> None:
    """§30.5: "dependent memory sources marked 'source removed'".

    The memory SURVIVES. Consent was given to Tara knowing it, and that
    consent did not expire with the thread it arrived on. This is the test
    that fails if someone ever "tidies up" the two scoped verbs into one.
    """
    message_id = ObjectId()
    memory = await _memory(store, source_message_id=message_id)

    marked = await service.on_conversation_deleted(user_id=USER_ID, message_ids=[message_id])

    assert marked == 1
    survivor = await store.get(USER_ID, memory.memory_id)
    assert survivor is not None, "a conversation delete must NOT delete memories"
    assert survivor.content, "and must not blank them either"
    assert survivor.visibility.source_state is SourceState.REMOVED
    assert survivor.source_message_id is None, "the jump-back target is what is lost"
    assert await _ledger_rows(db) == [], (
        "nothing was withdrawn — writing a withdrawal here would record a "
        "consent change that did not happen"
    )


async def test_the_two_scoped_verbs_do_not_do_each_others_job(
    service: MemoryService, store: MemoryStore
) -> None:
    """Stated as one assertion because it is the confusion worth naming."""
    journal_msg, convo_msg = ObjectId(), ObjectId()
    from_journal = await _memory(store, source_message_id=journal_msg)
    from_convo = await _memory(store, source_message_id=convo_msg)

    await service.on_journal_entry_deleted(
        user_id=USER_ID, message_ids=[journal_msg], delete_memories=True
    )
    await service.on_conversation_deleted(user_id=USER_ID, message_ids=[convo_msg])

    assert await store.get(USER_ID, from_journal.memory_id) is None  # ticked box deletes
    survivor = await store.get(USER_ID, from_convo.memory_id)
    assert survivor is not None  # conversation delete does not
    assert survivor.visibility.source_state is SourceState.REMOVED


# --- the vault is what proves it ------------------------------------------


async def test_the_vault_is_the_users_own_evidence(
    service: MemoryService, store: MemoryStore
) -> None:
    """§30.5 calls the vault her inventory of what Tara knows. After a delete
    it must no longer list the memory — that is the user-facing half of the
    proof, and `list_vault` deliberately shows muted and decayed rows, so a
    disappearance here means deletion and not merely quiet."""
    kept = await _memory(store, content="her father's shraddha falls in Bhadrapada")
    gone = await _memory(
        store, memory_type=MemoryType.MOOD_PATTERN, content="anxious about the move"
    )

    await service.forget(user_id=USER_ID, memory_id=gone.memory_id)

    listed = {m.memory_id for m in await service.vault(USER_ID)}
    assert listed == {kept.memory_id}


async def test_a_muted_memory_is_still_listed_and_is_not_a_deletion(
    service: MemoryService, store: MemoryStore, db
) -> None:
    """"Don't remember this" and "delete" are different promises (§30.5).
    Mute is reversible and stays in the inventory; only one of them writes a
    withdrawal."""
    memory = await _memory(store)

    await service.mute(user_id=USER_ID, memory_id=memory.memory_id, muted=True)

    listed = await service.vault(USER_ID)
    assert [m.memory_id for m in listed] == [memory.memory_id]
    assert listed[0].visibility.muted is True
    assert await _ledger_rows(db) == []


def _dt(value: dt.datetime) -> dt.datetime:  # pragma: no cover - readability helper
    return value
