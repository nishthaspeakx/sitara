"""§45 (CC-012) — the "in memory of" conversion.

§32.15 offers this as the alternative to deletion **on the same sheet**, which
means the two are read side by side by someone who has just lost a person.
Everything below is about the difference between them being real:

  · the deletion destroys and says so;
  · the conversion destroys NOTHING, and this file proves it collection by
    collection rather than by asserting a flag flipped.

The discipline is deliberately the deletions' own — what survives asserted as
hard as what dies — because the failure mode here is the worse direction. A
deletion that quietly kept something is a privacy bug found by an audit; a
conversion that quietly removed something is a bereaved user losing her
mother's birth chart because she chose the gentle option.
"""

from __future__ import annotations

import pytest
from bson import ObjectId

from sitara_api.family.models import MemorialState, Relation
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


# --- the default -----------------------------------------------------------


async def test_a_new_member_is_living(service: FamilyService) -> None:
    """§45 makes `living` the default, and a default is only a default if
    nobody has to pass it."""
    member = await service.add(
        owner_user_id=OWNER_ID, relation=Relation.FATHER, name="Ramesh", now=NOW
    )

    assert member.memorial_state is MemorialState.LIVING


# --- what the conversion does ----------------------------------------------


async def test_the_conversion_changes_the_state(service: FamilyService, db) -> None:
    member = await _member_with_everything(service, db)

    converted = await service.set_memorial_state(
        owner_user_id=OWNER_ID,
        member_id=member.member_id,
        state=MemorialState.IN_MEMORY,
        now=NOW,
    )

    assert converted is not None
    assert converted.memorial_state is MemorialState.IN_MEMORY
    assert (await service.get(OWNER_ID, member.member_id)).memorial_state is (
        MemorialState.IN_MEMORY
    )


async def test_the_member_stays_in_the_family_list(service: FamilyService, db) -> None:
    """§45: "the member remains in the family list". The point of the
    alternative is that she is still there."""
    member = await _member_with_everything(service, db)

    await service.set_memorial_state(
        owner_user_id=OWNER_ID, member_id=member.member_id, state=MemorialState.IN_MEMORY
    )

    listed = await service.list_members(OWNER_ID)
    assert [m.member_id for m in listed] == [member.member_id]


# --- what the conversion does NOT do (the whole entry) ---------------------


async def test_the_conversion_destroys_nothing(service: FamilyService, db) -> None:
    """§45.2: "non-destructive by construction". Asserted collection by
    collection, because "nothing was destroyed" is not a thing a flag can
    prove."""
    member = await _member_with_everything(service, db, name="Sudha")
    memory = await MemoryStore(db).create(
        user_id=OWNER_ID,
        memory_type=MemoryType.PERSON,
        content="Sudha takes her walk before the heat",
        consent=consent_for(MemoryType.PERSON),
        embedding=None,
        now=NOW,
    )
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

    await service.set_memorial_state(
        owner_user_id=OWNER_ID, member_id=member.member_id, state=MemorialState.IN_MEMORY
    )

    assert await db.birth_details.count_documents({"family_member_id": member.member_id}) == 1
    assert await db.charts.count_documents({"subject_id": member.member_id}) == 1
    assert await db.family_members.count_documents({"_id": member.member_id}) == 1
    assert await MemoryStore(db).get(OWNER_ID, memory.memory_id) is not None
    assert await db.night_reflections.count_documents({"user_id": OWNER_ID}) == 1


async def test_the_conversion_writes_no_withdrawal(service: FamilyService, db) -> None:
    """CC-011 §44.5's ledger records consent WITHDRAWN. Nothing was withdrawn
    here, and a row saying otherwise would be a false entry in a permanent
    legal record."""
    member = await _member_with_everything(service, db)
    before = await db.consents.count_documents({"user_id": OWNER_ID})

    await service.set_memorial_state(
        owner_user_id=OWNER_ID, member_id=member.member_id, state=MemorialState.IN_MEMORY
    )

    assert await db.consents.count_documents({"user_id": OWNER_ID}) == before
    attestation = await db.consents.find_one(
        {"user_id": OWNER_ID, "type": "family.attestation"}
    )
    assert attestation is not None
    assert attestation["revoked_at"] is None, "she withdrew nothing"


async def test_the_conversion_touches_exactly_one_field(
    service: FamilyService, db
) -> None:
    """§45.2: "writes one field and touches no other collection".

    Compared document to document, so a future helpful addition — clearing a
    language tag, blanking a relation — fails here rather than in someone's
    family list.
    """
    member = await _member_with_everything(service, db)
    before = await db.family_members.find_one({"_id": member.member_id})

    await service.set_memorial_state(
        owner_user_id=OWNER_ID, member_id=member.member_id, state=MemorialState.IN_MEMORY
    )

    after = await db.family_members.find_one({"_id": member.member_id})
    changed = {
        key
        for key in set(before) | set(after)
        if before.get(key) != after.get(key)
    }
    assert changed == {"memorial_state", "updated_at"}


# --- reversibility ---------------------------------------------------------


async def test_the_conversion_is_reversible(service: FamilyService, db) -> None:
    """§45.2: "a wrong tap at that moment must not be another loss"."""
    member = await _member_with_everything(service, db)

    await service.set_memorial_state(
        owner_user_id=OWNER_ID, member_id=member.member_id, state=MemorialState.IN_MEMORY
    )
    restored = await service.set_memorial_state(
        owner_user_id=OWNER_ID, member_id=member.member_id, state=MemorialState.LIVING
    )

    assert restored is not None
    assert restored.memorial_state is MemorialState.LIVING


# --- the two paths remain distinct ----------------------------------------


async def test_a_memorial_member_can_still_be_deleted_with_the_full_radius(
    service: FamilyService, db
) -> None:
    """§45.3: the conversion is an ALTERNATIVE, never a replacement. Someone
    who converts and later decides otherwise gets §32.15's radius unchanged."""
    member = await _member_with_everything(service, db)
    await service.set_memorial_state(
        owner_user_id=OWNER_ID, member_id=member.member_id, state=MemorialState.IN_MEMORY
    )

    effects = await service.delete(owner_user_id=OWNER_ID, member_id=member.member_id)

    assert effects.member_removed is True
    assert effects.birth_details == 1
    assert effects.charts == 1
    assert effects.attestation_retained is True


async def test_deleting_a_living_member_is_unchanged_by_this_entry(
    service: FamilyService, db
) -> None:
    """A regression guard on §32.15: CC-012 added a field, not a behaviour."""
    member = await _member_with_everything(service, db)

    effects = await service.delete(owner_user_id=OWNER_ID, member_id=member.member_id)

    assert effects.member_removed is True
    assert await db.charts.count_documents({"subject_id": member.member_id}) == 0


# --- ownership -------------------------------------------------------------


async def test_one_account_cannot_convert_anothers_member(
    service: FamilyService, db
) -> None:
    member = await _member_with_everything(service, db)

    result = await service.set_memorial_state(
        owner_user_id=OTHER_OWNER_ID,
        member_id=member.member_id,
        state=MemorialState.IN_MEMORY,
    )

    assert result is None
    assert (await service.get(OWNER_ID, member.member_id)).memorial_state is (
        MemorialState.LIVING
    )


# --- §23.2's reminders -----------------------------------------------------


async def test_a_memorial_member_is_excluded_from_forward_looking_reminders(
    service: FamilyService, db
) -> None:
    """§45.2: birthday and anniversary reminders stop firing as forward-looking
    prompts.

    The exclusion is a QUERY, not a deletion — `reminder_candidates` filters on
    the state, so the member is still listed, still charted, still in the
    journal, and simply not the subject of "her birthday is on Sunday" three
    days after her funeral.
    """
    living = await service.add(
        owner_user_id=OWNER_ID, relation=Relation.DAUGHTER, name="Ananya", now=NOW
    )
    departed = await _member_with_everything(service, db, name="Sudha")
    await service.set_memorial_state(
        owner_user_id=OWNER_ID, member_id=departed.member_id, state=MemorialState.IN_MEMORY
    )

    candidates = await service.reminder_candidates(OWNER_ID)

    assert [m.member_id for m in candidates] == [living.member_id]
    # …and she is still in the family list, which is the whole difference.
    assert {m.member_id for m in await service.list_members(OWNER_ID)} == {
        living.member_id,
        departed.member_id,
    }
