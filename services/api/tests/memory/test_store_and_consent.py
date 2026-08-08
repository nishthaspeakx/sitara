"""§32.4 consent, §6.4 storage, §30.5 deletion — against the real validators."""

from __future__ import annotations

import datetime as dt

import pytest
from bson import ObjectId

from sitara_api.memory.models import (
    ConsentRecord,
    ConsentRequired,
    MedicalContentDeclined,
    SourceState,
)
from sitara_api.memory.taxonomy import RECONFIRM_WORDING, MemoryType
from tests.memory.conftest import NOW, OTHER_USER_ID, USER_ID, consent_for


async def _store_one(store, memory_type=MemoryType.PERSON, content="Priya is my sister", **kw):  # noqa: ANN001, ANN003
    return await store.create(
        user_id=kw.pop("user_id", USER_ID),
        memory_type=memory_type,
        content=content,
        consent=kw.pop("consent", consent_for(memory_type, wording=content)),
        embedding=kw.pop("embedding", None),
        now=kw.pop("now", NOW),
        **kw,
    )


class TestConsent:
    @pytest.mark.asyncio
    async def test_an_accepted_chip_is_stored_with_its_stamp(self, store) -> None:  # noqa: ANN001
        memory = await _store_one(store)

        assert memory.consent.granted
        assert memory.consent.granted_at == NOW
        assert memory.consent.history[0].wording == "Priya is my sister"

    @pytest.mark.asyncio
    async def test_nothing_is_stored_without_a_chip(self, store) -> None:  # noqa: ANN001
        """§32.4: "all types explicit-chip". There is no path around this."""
        with pytest.raises(ConsentRequired):
            await _store_one(
                store,
                consent=ConsentRecord(granted=False, granted_at=NOW),
            )

    @pytest.mark.parametrize("memory_type", sorted(RECONFIRM_WORDING))
    @pytest.mark.asyncio
    async def test_types_7_to_9_refuse_unconfirmed_wording(self, store, memory_type) -> None:  # noqa: ANN001
        """§32.4: "types 7–9 always re-confirm wording before save"."""
        with pytest.raises(ConsentRequired, match="re-confirmed"):
            await _store_one(
                store,
                memory_type,
                content="something personal",
                consent=ConsentRecord(granted=True, granted_at=NOW, wording_reconfirmed=False),
            )

    @pytest.mark.asyncio
    async def test_types_7_to_9_store_once_wording_is_confirmed(self, store) -> None:  # noqa: ANN001
        memory = await _store_one(
            store, MemoryType.MOOD_PATTERN, content="Mondays feel restless"
        )

        assert memory.type is MemoryType.MOOD_PATTERN
        assert memory.consent.wording_reconfirmed

    @pytest.mark.asyncio
    async def test_a_diagnosis_is_declined_at_classification(self, store) -> None:  # noqa: ANN001
        """§32.4: health-adjacent is "non-medical framing; NEVER
        symptoms/diagnoses — those are declined at classification"."""
        with pytest.raises(MedicalContentDeclined):
            await _store_one(
                store,
                MemoryType.HEALTH_ADJACENT,
                content="I was diagnosed with high blood pressure last month",
            )

    @pytest.mark.asyncio
    async def test_non_medical_wellbeing_notes_are_fine(self, store) -> None:  # noqa: ANN001
        memory = await _store_one(
            store, MemoryType.HEALTH_ADJACENT, content="I walk every morning before work"
        )

        assert memory.type is MemoryType.HEALTH_ADJACENT


class TestStorage:
    @pytest.mark.asyncio
    async def test_the_document_passes_the_64_validator(self, store, db, embedder) -> None:  # noqa: ANN001
        memory = await _store_one(store, embedding=embedder.embed_one("Priya is my sister"))

        doc = await db.memories.find_one({"_id": memory.memory_id})
        assert doc is not None
        assert isinstance(doc["user_id"], ObjectId)
        assert doc["type"] == "person"
        assert len(doc["embedding"]) == 1024  # §6.4's index width
        assert doc["decay_score"] == 1.0
        assert doc["schema_v"]  # §6.4 stamps every document

    @pytest.mark.asyncio
    async def test_a_memory_can_be_stored_without_an_embedding(self, store, db) -> None:  # noqa: ANN001
        """§32.5: embeddings are derived data, never the source of truth. An
        embedder outage must not lose a memory the user consented to."""
        memory = await _store_one(store, embedding=None)

        doc = await db.memories.find_one({"_id": memory.memory_id})
        assert doc["embedding"] is None
        assert not memory.has_embedding

    @pytest.mark.asyncio
    async def test_the_vault_is_scoped_to_one_user(self, store) -> None:  # noqa: ANN001
        await _store_one(store, content="mine")
        await _store_one(store, content="someone else's", user_id=OTHER_USER_ID)

        mine = await store.list_vault(USER_ID)
        assert [m.content for m in mine] == ["mine"]

    @pytest.mark.asyncio
    async def test_the_vault_filters_by_the_11_labels(self, store) -> None:  # noqa: ANN001
        await _store_one(store, MemoryType.PERSON, content="Priya")
        await _store_one(store, MemoryType.PREFERENCE, content="tea without sugar")

        only = await store.list_vault(USER_ID, types=[MemoryType.PREFERENCE])
        assert [m.type for m in only] == [MemoryType.PREFERENCE]


class TestVaultEditing:
    @pytest.mark.asyncio
    async def test_an_edit_reconsents_and_resets_decay(self, store, embedder) -> None:  # noqa: ANN001
        """§30.5: "correct a memory" → future guidance uses the corrected
        version. A corrected memory is current again, so decay resets."""
        memory = await _store_one(store, MemoryType.PREFERENCE, content="tea with sugar")
        await store.set_decay_scores([(memory.memory_id, 0.3)])

        edited = await store.edit(
            user_id=USER_ID,
            memory_id=memory.memory_id,
            content="tea without sugar",
            embedding=embedder.embed_one("tea without sugar"),
        )

        assert edited is not None
        assert edited.content == "tea without sugar"
        assert edited.decay_score == 1.0
        assert edited.consent.history[-1].action.value == "edited"
        assert edited.consent.history[-1].wording == "tea without sugar"

    @pytest.mark.asyncio
    async def test_muting_withholds_without_destroying(self, store) -> None:  # noqa: ANN001
        """§30.5's "don't remember this" is reversible; deletion is not."""
        memory = await _store_one(store)

        muted = await store.set_muted(user_id=USER_ID, memory_id=memory.memory_id, muted=True)
        assert muted is not None and muted.visibility.muted
        # Still in the vault — it is the user's inventory, not a ranking.
        assert len(await store.list_vault(USER_ID)) == 1

        unmuted = await store.set_muted(user_id=USER_ID, memory_id=memory.memory_id, muted=False)
        assert unmuted is not None and not unmuted.visibility.muted

    @pytest.mark.asyncio
    async def test_one_user_cannot_edit_anothers_memory(self, store) -> None:  # noqa: ANN001
        memory = await _store_one(store, user_id=OTHER_USER_ID)

        assert await store.edit(
            user_id=USER_ID, memory_id=memory.memory_id, content="mine now", embedding=None
        ) is None


class TestDeletion:
    @pytest.mark.asyncio
    async def test_delete_is_hard_and_takes_the_embedding(self, store, db, embedder) -> None:  # noqa: ANN001
        """Diagram 8: "Delete = hard delete + embedding removed". No
        tombstone — the vector lives in the document and leaves with it."""
        memory = await _store_one(store, embedding=embedder.embed_one("Priya"))

        assert await store.delete(user_id=USER_ID, memory_id=memory.memory_id)
        assert await db.memories.find_one({"_id": memory.memory_id}) is None
        assert await db.memories.count_documents({}) == 0

    @pytest.mark.asyncio
    async def test_one_user_cannot_delete_anothers_memory(self, store) -> None:  # noqa: ANN001
        memory = await _store_one(store, user_id=OTHER_USER_ID)

        assert not await store.delete(user_id=USER_ID, memory_id=memory.memory_id)

    @pytest.mark.asyncio
    async def test_account_deletion_removes_every_memory_and_vector(self, store, db) -> None:  # noqa: ANN001
        """§13: deletion removes application records, embeddings included."""
        await _store_one(store, content="a")
        await _store_one(store, content="b")
        await _store_one(store, content="theirs", user_id=OTHER_USER_ID)

        assert await store.delete_all_for_user(USER_ID) == 2
        assert await db.memories.count_documents({"user_id": USER_ID}) == 0
        assert await db.memories.count_documents({"user_id": OTHER_USER_ID}) == 1


class TestScopedDeletion:
    """§30.5: "deleting has scoped, stated effects"."""

    @pytest.mark.asyncio
    async def test_a_deleted_journal_entry_leaves_memories_alone_by_default(
        self, store, service
    ) -> None:  # noqa: ANN001
        """"memories sourced from it survive unless also deleted — offered as
        a checkbox". Unticked is the default."""
        source = ObjectId()
        await _store_one(store, source_message_id=source)

        removed = await service.on_journal_entry_deleted(
            user_id=USER_ID, message_ids=[source], delete_memories=False
        )

        assert removed == 0
        assert len(await store.list_vault(USER_ID)) == 1

    @pytest.mark.asyncio
    async def test_ticking_the_checkbox_deletes_them(self, store, service) -> None:  # noqa: ANN001
        source = ObjectId()
        await _store_one(store, source_message_id=source)

        removed = await service.on_journal_entry_deleted(
            user_id=USER_ID, message_ids=[source], delete_memories=True
        )

        assert removed == 1
        assert await store.list_vault(USER_ID) == []

    @pytest.mark.asyncio
    async def test_a_deleted_conversation_marks_the_source_removed(
        self, store, service
    ) -> None:  # noqa: ANN001
        """§30.5: "dependent memory sources marked 'source removed'". The
        memory survives — consent to Tara knowing it did not expire with the
        thread it came from."""
        source = ObjectId()
        await _store_one(store, source_message_id=source)

        marked = await service.on_conversation_deleted(user_id=USER_ID, message_ids=[source])

        (memory,) = await store.list_vault(USER_ID)
        assert marked == 1
        assert memory.visibility.source_state is SourceState.REMOVED
        assert memory.source_message_id is None
        assert memory.content  # the memory itself is untouched

    @pytest.mark.asyncio
    async def test_scoped_effects_do_not_reach_another_users_memories(
        self, store, service
    ) -> None:  # noqa: ANN001
        source = ObjectId()
        await _store_one(store, user_id=OTHER_USER_ID, source_message_id=source)

        assert await service.on_conversation_deleted(user_id=USER_ID, message_ids=[source]) == 0

    @pytest.mark.asyncio
    async def test_an_empty_id_list_is_a_no_op(self, store, service) -> None:  # noqa: ANN001
        await _store_one(store)

        assert await service.on_conversation_deleted(user_id=USER_ID, message_ids=[]) == 0
        assert len(await store.list_vault(USER_ID)) == 1


class TestConsentLedger:
    @pytest.mark.asyncio
    async def test_the_ledger_survives_a_round_trip(self, store) -> None:  # noqa: ANN001
        """§13: "consent ledger visible in-app" — so it must read back."""
        await _store_one(store, MemoryType.WORK_FINANCE, content="I work from home")

        (loaded,) = await store.list_vault(USER_ID)
        assert loaded.consent.granted
        assert loaded.consent.wording_reconfirmed
        assert loaded.consent.history[0].at == NOW
        assert isinstance(loaded.consent.history[0].at, dt.datetime)
