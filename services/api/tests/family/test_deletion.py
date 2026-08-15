"""§32.15 — the fourth blast radius.

§30.5 gives three deletions different consequences; §32.15 adds a fourth and
it is the one with the most moving parts: birth details and charts are
destroyed, memories are offered but kept by default, past journal text is
untouched, reminders and rankings drop the member immediately, and the
attestation consent record SURVIVES because it is a legal-basis fact about the
account-holder rather than data about the person deleted.

That last one is the counter-intuitive half, and the one a well-meaning
"delete everything" would get wrong. It also happens to be the precedent
CC-011 §44.5 borrowed for memory withdrawals, so a regression here quietly
undermines that too.
"""

from __future__ import annotations

import pytest
from bson import ObjectId

from sitara_api.family.models import Relation
from sitara_api.family.service import FamilyService
from sitara_api.family.store import FamilyStore
from sitara_api.memory.embeddings import DeterministicEmbedder
from sitara_api.memory.retrieval import ExactVectorSearch
from sitara_api.memory.service import MemoryService
from sitara_api.memory.store import MemoryStore
from sitara_api.memory.taxonomy import MemoryType
from tests.family.conftest import NOW, OTHER_OWNER_ID, OWNER_ID
from tests.memory.conftest import consent_for

pytestmark = pytest.mark.asyncio


@pytest.fixture()
def memory_service(db) -> MemoryService:  # noqa: ANN001
    store = MemoryStore(db)
    return MemoryService(
        store=store, search=ExactVectorSearch(store), embedder=DeterministicEmbedder()
    )


@pytest.fixture()
def service(store: FamilyStore, memory_service: MemoryService) -> FamilyService:
    return FamilyService(store=store, memory_service=memory_service)


async def _member_with_everything(service: FamilyService, db, *, name: str = "Sudha"):
    """A member with attested birth details, a computed chart, and a memory."""
    member = await service.add(
        owner_user_id=OWNER_ID,
        relation=Relation.MOTHER,
        name=name,
        language_tag="hi",
        now=NOW,
    )
    await service.attest_birth_details(
        owner_user_id=OWNER_ID, member_id=member.member_id, now=NOW
    )
    await db.birth_details.insert_one(
        {
            "_id": ObjectId(),
            "user_id": None,
            "family_member_id": member.member_id,
            "date": "1958-03-11",
            "time": "05:40",
            "time_accuracy": "exact",
            "place": {"city": "Kanpur"},
            "tz_snapshot": {"zone": "Asia/Kolkata"},
            "created_at": NOW,
            "updated_at": NOW,
            "schema_v": 1,
        }
    )
    await db.charts.insert_one(
        {
            "_id": ObjectId(),
            "subject_id": member.member_id,
            "engine_version": "0.1.0",
            "ayanamsa": "lahiri",
            "facts": [],
            "fact_ids": [],
            "parity_status": "verified",
            "created_at": NOW,
            "updated_at": NOW,
            "schema_v": 1,
        }
    )
    return member


# --- what dies -------------------------------------------------------------


async def test_deleting_a_member_hard_deletes_birth_details_and_charts(
    service: FamilyService, db
) -> None:
    """§32.15's first clause, and §13's crown jewels leaving with them."""
    member = await _member_with_everything(service, db)

    effects = await service.delete(owner_user_id=OWNER_ID, member_id=member.member_id)

    assert effects.birth_details == 1
    assert effects.charts == 1
    assert effects.member_removed is True
    assert await db.birth_details.count_documents({"family_member_id": member.member_id}) == 0
    assert await db.charts.count_documents({"subject_id": member.member_id}) == 0
    assert await db.family_members.count_documents({"_id": member.member_id}) == 0


async def test_the_member_leaves_reminders_and_rankings_immediately(
    service: FamilyService, db
) -> None:
    """§32.15: "removes them from reminders/rankings immediately".

    Immediately is doing work in that sentence. The ranking engine reads
    `family_members` for §28.2's family_reminder, so the removal IS the
    mechanism — there is no queue to drain and no cache to expire, and this
    test is what says so.
    """
    member = await _member_with_everything(service, db)

    await service.delete(owner_user_id=OWNER_ID, member_id=member.member_id)

    assert await service.list_members(OWNER_ID) == []


# --- what survives ---------------------------------------------------------


async def test_the_attestation_consent_record_is_retained(
    service: FamilyService, db
) -> None:
    """§32.15: "DPDP-clean: the attestation consent record is retained (legal
    basis history), the data is not."

    The consent is a fact about the ACCOUNT-HOLDER — that she once asserted
    she had the right to enter someone's birth details. Deleting it would
    destroy her own record of her own act, which is the opposite of what a
    deletion right is for.
    """
    member = await _member_with_everything(service, db)

    effects = await service.delete(owner_user_id=OWNER_ID, member_id=member.member_id)

    assert effects.attestation_retained is True
    rows = [doc async for doc in db.consents.find({"user_id": OWNER_ID})]
    attestations = [r for r in rows if r["type"].startswith("family.attestation")]
    assert len(attestations) == 1
    assert attestations[0]["revoked_at"] is not None, "she withdrew it, and that is recorded"


async def test_the_attestation_record_names_no_deleted_person(
    service: FamilyService, db
) -> None:
    """A retained record that still holds the name is not "the data is not"."""
    member = await _member_with_everything(service, db, name="Sudha")

    await service.delete(owner_user_id=OWNER_ID, member_id=member.member_id)

    rows = [doc async for doc in db.consents.find({"user_id": OWNER_ID})]
    assert "Sudha" not in repr(rows)
    assert str(member.member_id) not in repr(rows)


async def test_memories_about_the_member_are_kept_by_default(
    service: FamilyService, memory_service: MemoryService, db
) -> None:
    """§32.15: "default keep". The checkbox starts unticked and an unticked
    checkbox is inert — the same promise §30.5 makes for journal entries."""
    member = await _member_with_everything(service, db, name="Sudha")
    memory = await MemoryStore(db).create(
        user_id=OWNER_ID,
        memory_type=MemoryType.PERSON,
        content="Sudha takes her walk before the heat",
        consent=consent_for(MemoryType.PERSON),
        embedding=None,
        now=NOW,
    )

    effects = await service.delete(owner_user_id=OWNER_ID, member_id=member.member_id)

    assert effects.memories == 0
    assert await MemoryStore(db).get(OWNER_ID, memory.memory_id) is not None


async def test_past_journal_text_is_unchanged(service: FamilyService, db) -> None:
    """§32.15: "keeps past journal text (stated)".

    What Tara said in a brief last March was true when she said it. Rewriting
    history to erase a person is not deletion, it is revision.
    """
    member = await _member_with_everything(service, db, name="Sudha")
    await db.night_reflections.insert_one(
        {
            "_id": ObjectId(),
            "user_id": OWNER_ID,
            "date": "2026-03-11",
            "entries": ["Sudha's birthday — called her in the morning"],
            "memory_chips": [],
            "locale": "en",
            "created_at": NOW,
            "updated_at": NOW,
            "schema_v": 1,
        }
    )

    await service.delete(owner_user_id=OWNER_ID, member_id=member.member_id)

    reflection = await db.night_reflections.find_one({"user_id": OWNER_ID})
    assert reflection is not None
    assert "Sudha" in reflection["entries"][0]


# --- the checkbox ----------------------------------------------------------


async def test_the_candidate_memories_are_listed_before_they_are_deleted(
    service: FamilyService, db
) -> None:
    """§32.15: "(default keep, **listed**)".

    `memories` has no family-member field in §6.4, so "about them" is a
    judgement. Listing the candidates puts that judgement in front of the
    person whose memories they are, instead of behind a checkbox that deletes
    whatever the software guessed.
    """
    member = await _member_with_everything(service, db, name="Sudha")
    store = MemoryStore(db)
    about = await store.create(
        user_id=OWNER_ID,
        memory_type=MemoryType.PERSON,
        content="Sudha takes her walk before the heat",
        consent=consent_for(MemoryType.PERSON),
        embedding=None,
        now=NOW,
    )
    unrelated = await store.create(
        user_id=OWNER_ID,
        memory_type=MemoryType.PREFERENCE,
        content="drinks filter coffee, never instant",
        consent=consent_for(MemoryType.PREFERENCE),
        embedding=None,
        now=NOW,
    )

    candidates = await service.memories_about(
        owner_user_id=OWNER_ID, member_id=member.member_id
    )

    ids = {c.memory_id for c in candidates}
    assert about.memory_id in ids
    assert unrelated.memory_id not in ids


async def test_ticking_the_box_deletes_only_the_ticked_memories(
    service: FamilyService, db
) -> None:
    """The user ticks specific rows, not a category. Passing ids rather than
    a boolean is what makes "listed" mean something."""
    member = await _member_with_everything(service, db, name="Sudha")
    store = MemoryStore(db)
    doomed = await store.create(
        user_id=OWNER_ID,
        memory_type=MemoryType.PERSON,
        content="Sudha takes her walk before the heat",
        consent=consent_for(MemoryType.PERSON),
        embedding=None,
        now=NOW,
    )
    spared = await store.create(
        user_id=OWNER_ID,
        memory_type=MemoryType.DATE_ANNIVERSARY,
        content="Sudha's birthday is 11 March",
        consent=consent_for(MemoryType.DATE_ANNIVERSARY),
        embedding=None,
        now=NOW,
    )

    effects = await service.delete(
        owner_user_id=OWNER_ID,
        member_id=member.member_id,
        delete_memory_ids=[doomed.memory_id],
    )

    assert effects.memories == 1
    assert await store.get(OWNER_ID, doomed.memory_id) is None
    assert await store.get(OWNER_ID, spared.memory_id) is not None


async def test_a_deleted_memory_still_writes_its_withdrawal(
    service: FamilyService, db
) -> None:
    """CC-011 §44.5 applies wherever a memory dies, not only in the vault."""
    member = await _member_with_everything(service, db, name="Sudha")
    memory = await MemoryStore(db).create(
        user_id=OWNER_ID,
        memory_type=MemoryType.PERSON,
        content="Sudha takes her walk before the heat",
        consent=consent_for(MemoryType.PERSON),
        embedding=None,
        now=NOW,
    )

    await service.delete(
        owner_user_id=OWNER_ID,
        member_id=member.member_id,
        delete_memory_ids=[memory.memory_id],
    )

    withdrawals = [
        doc
        async for doc in db.consents.find({"user_id": OWNER_ID, "type": "memory.person"})
    ]
    assert len(withdrawals) == 1


async def test_a_memory_id_that_is_not_hers_is_ignored(
    service: FamilyService, db
) -> None:
    """The ids come from a client. A delete scoped by "whatever ids you send"
    would let one account name another's memory."""
    member = await _member_with_everything(service, db)
    store = MemoryStore(db)
    someone_elses = await store.create(
        user_id=OTHER_OWNER_ID,
        memory_type=MemoryType.PERSON,
        content="a memory belonging to another account",
        consent=consent_for(MemoryType.PERSON),
        embedding=None,
        now=NOW,
    )

    effects = await service.delete(
        owner_user_id=OWNER_ID,
        member_id=member.member_id,
        delete_memory_ids=[someone_elses.memory_id],
    )

    assert effects.memories == 0
    assert await store.get(OTHER_OWNER_ID, someone_elses.memory_id) is not None


# --- ownership -------------------------------------------------------------


async def test_one_account_cannot_delete_anothers_family_member(
    service: FamilyService, db
) -> None:
    member = await _member_with_everything(service, db)

    effects = await service.delete(owner_user_id=OTHER_OWNER_ID, member_id=member.member_id)

    assert effects.member_removed is False
    assert effects.birth_details == 0
    assert await db.family_members.count_documents({"_id": member.member_id}) == 1
    assert await db.birth_details.count_documents({"family_member_id": member.member_id}) == 1


async def test_the_in_memory_alternative_exists_beside_this_deletion() -> None:
    """§32.15 offers "in memory of" **on the same sheet** as the deletion.

    This file's predecessor asserted the alternative was UNBUILT — the marker
    that made the gap visible in a test run rather than leaving it to be found
    by a grieving user offered only the destructive option. CC-012 (§45) built
    it, the marker fired, and this replaced it.

    What is asserted now is that both paths still exist. A future tidy-up that
    collapsed them — "the memorial state is just a soft delete" — would put
    the product back where it started, and §45.3 keeps them separate on
    purpose: one destroys and says so, the other destroys nothing.
    """
    from sitara_api.family.models import MemorialState
    from sitara_api.family.service import FamilyService

    assert MemorialState.IN_MEMORY
    assert hasattr(FamilyService, "set_memorial_state")
    assert hasattr(FamilyService, "delete"), "the alternative did not replace it"
