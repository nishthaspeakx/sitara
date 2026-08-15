"""The `memories` collection (§6.4), the vault (§30.5) and consent (§32.4).

Two rules shape every method here:

* **Nothing is stored without an explicit chip.** There is no `save()` that
  takes content and a type; the only entry point takes a `ConsentRecord`, and
  it refuses a type 7–9 memory whose wording was not re-confirmed. Making that
  a signature rather than a check means no future caller can forget.
* **Delete means gone.** Diagram 8: "Delete = hard delete + embedding
  removed". Not a tombstone, not `deleted: true` — the document leaves the
  collection, and the vector leaves with it because it lives in the same
  document. §30.5's scoped effects are about OTHER things the deletion touches,
  never about softening this one.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Sequence
from typing import Any

from bson import ObjectId

from sitara_api.db.documents import stamp
from sitara_api.memory.embeddings import Embedding
from sitara_api.memory.models import (
    ConsentAction,
    ConsentEvent,
    ConsentRecord,
    ConsentRequired,
    MedicalContentDeclined,
    Memory,
    SourceState,
    Visibility,
)
from sitara_api.memory.taxonomy import (
    RECONFIRM_WORDING,
    MemoryType,
    is_medical_content,
)

logger = logging.getLogger(__name__)

#: §29.1's S25 — the Memory Vault. The surface a withdrawal was made from is
#: part of the §13 ledger's record, the same way onboarding stamps "S05".
WITHDRAWAL_SURFACE = "S25"


class MemoryStore:
    def __init__(self, db: Any) -> None:
        self._db = db

    # -- create ------------------------------------------------------------

    async def create(
        self,
        *,
        user_id: ObjectId,
        memory_type: MemoryType,
        content: str,
        consent: ConsentRecord,
        embedding: Embedding | None,
        source_message_id: ObjectId | None = None,
        now: dt.datetime | None = None,
    ) -> Memory:
        """Store one accepted chip. Raises rather than storing a doubtful one."""
        if not consent.granted:
            raise ConsentRequired(f"{memory_type} requires an explicit consent chip (§32.4)")
        if memory_type in RECONFIRM_WORDING and not consent.wording_reconfirmed:
            raise ConsentRequired(
                f"{memory_type} is a §32.4 type 7–9 memory — its wording must be "
                "re-confirmed with the user before it can be saved"
            )
        if memory_type is MemoryType.HEALTH_ADJACENT and is_medical_content(content):
            # §32.4: "NEVER symptoms/diagnoses — those are declined at
            # classification". Declining here too, because classification is a
            # model and this is not.
            raise MedicalContentDeclined(
                "health-adjacent memories carry non-medical framing only (§32.4)"
            )

        document = stamp(
            {
                "user_id": user_id,
                "type": memory_type.value,
                "content": content,
                "embedding": list(embedding.vector) if embedding else None,
                "embedding_model": embedding.model if embedding else None,
                "consent": consent.to_doc(),
                "visibility": Visibility().to_doc(),
                "source_message_id": source_message_id,
                "decay_score": 1.0,
            },
            now=now,
        )
        result = await self._db.memories.insert_one(document)
        document["_id"] = result.inserted_id
        return Memory.from_doc(document)

    # -- read --------------------------------------------------------------

    async def get(self, user_id: ObjectId, memory_id: ObjectId) -> Memory | None:
        doc = await self._db.memories.find_one({"_id": memory_id, "user_id": user_id})
        return Memory.from_doc(doc) if doc else None

    async def list_vault(
        self,
        user_id: ObjectId,
        *,
        types: Sequence[MemoryType] | None = None,
        limit: int = 200,
    ) -> list[Memory]:
        """§30.5: "the 11 typed facts with consent stamps — never a content
        archive". The vault shows everything, including decayed and muted
        memories: it is the user's inventory of what Tara knows, not a
        retrieval ranking."""
        query: dict[str, Any] = {"user_id": user_id}
        if types:
            query["type"] = {"$in": [t.value for t in types]}
        cursor = self._db.memories.find(query).sort("created_at", -1).limit(limit)
        return [Memory.from_doc(doc) async for doc in cursor]

    async def candidates_for_search(
        self, user_id: ObjectId, *, limit: int = 500
    ) -> list[tuple[Memory, list[float] | None, str | None]]:
        """Everything searchable for one user — the dev fallback's input.

        Returns the vector alongside the memory because exact search needs it
        and `Memory` deliberately does not carry 1024 floats around.
        """
        cursor = self._db.memories.find({"user_id": user_id}).limit(limit)
        rows: list[tuple[Memory, list[float] | None, str | None]] = []
        async for doc in cursor:
            rows.append((Memory.from_doc(doc), doc.get("embedding"), doc.get("embedding_model")))
        return rows

    # -- update ------------------------------------------------------------

    async def edit(
        self,
        *,
        user_id: ObjectId,
        memory_id: ObjectId,
        content: str,
        embedding: Embedding | None,
        now: dt.datetime | None = None,
    ) -> Memory | None:
        """§30.5: "correct a memory" → vault edit with effect preview.

        An edit re-consents by definition — the user just told us the wording —
        and resets decay, because a corrected memory is current again.
        """
        moment = now or dt.datetime.now(dt.UTC)
        existing = await self.get(user_id, memory_id)
        if existing is None:
            return None
        event = ConsentEvent(action=ConsentAction.EDITED, at=moment, wording=content)
        consent = ConsentRecord(
            granted=True,
            granted_at=existing.consent.granted_at,
            wording_reconfirmed=True,
            history=(*existing.consent.history, event),
        )
        update: dict[str, Any] = {
            "content": content,
            "consent": consent.to_doc(),
            "decay_score": 1.0,
            "updated_at": moment,
        }
        if embedding is not None:
            update["embedding"] = list(embedding.vector)
            update["embedding_model"] = embedding.model
        await self._db.memories.update_one({"_id": memory_id, "user_id": user_id}, {"$set": update})
        return await self.get(user_id, memory_id)

    async def set_muted(
        self, *, user_id: ObjectId, memory_id: ObjectId, muted: bool
    ) -> Memory | None:
        """§30.5's "don't remember this" on a chip or past message, without
        destroying the record the user may want back."""
        memory = await self.get(user_id, memory_id)
        if memory is None:
            return None
        visibility = Visibility(muted=muted, source_state=memory.visibility.source_state)
        await self._db.memories.update_one(
            {"_id": memory_id, "user_id": user_id},
            {"$set": {"visibility": visibility.to_doc(), "updated_at": dt.datetime.now(dt.UTC)}},
        )
        return await self.get(user_id, memory_id)

    async def set_decay_scores(self, updates: Sequence[tuple[ObjectId, float]]) -> int:
        """Bulk write for the nightly consolidation job (§32.4)."""
        written = 0
        for memory_id, score in updates:
            await self._db.memories.update_one(
                {"_id": memory_id}, {"$set": {"decay_score": score}}
            )
            written += 1
        return written

    # -- delete (§30.5) ----------------------------------------------------

    async def delete(self, *, user_id: ObjectId, memory_id: ObjectId) -> bool:
        """Hard delete, embedding included (diagram 8).

        §30.5 states the scope at the confirm step: Tara stops knowing this;
        past journal text is unchanged. Both halves are true here because the
        journal never stored a copy — it links, and this row is gone.
        """
        result = await self._db.memories.delete_one({"_id": memory_id, "user_id": user_id})
        return result.deleted_count == 1

    async def record_withdrawal(
        self,
        *,
        user_id: ObjectId,
        memory_type: MemoryType,
        granted_at: dt.datetime | None,
        surface: str = WITHDRAWAL_SURFACE,
        now: dt.datetime | None = None,
    ) -> None:
        """Write a memory withdrawal to the §13 consent ledger (CC-011 §44.5).

        This is the one method here that writes to a collection other than
        `memories`, and it exists because the two policies had no meeting
        point. §13 requires a "consent ledger visible in-app"; §30.5's delete
        is a hard delete; and a memory's consent history lives INSIDE the
        deleted document — so withdrawing consent destroyed the only evidence
        that consent had ever been withdrawn. A user could not prove her own
        deletion, which is the one thing a vault is for.

        The row is **content-free**: the §32.4 type, when consent was granted,
        when it was withdrawn, and the surface. Not the content, and not the
        memory's `_id` — an id is a handle on the deleted row and a ledger full
        of them is a catalogue of what she chose to erase. §32.15 settled this
        shape already for family members: "the attestation consent record is
        retained (legal basis history), the data is not".

        It APPENDS rather than upserting, unlike `onboarding.record_consent`.
        Consenting twice to the same policy is one consent, so that one
        upserts on (user_id, type); withdrawing two memories of the same type
        is two withdrawals, and §6.4's `user_id+type` index is not unique.
        """
        moment = now or dt.datetime.now(dt.UTC)
        await self._db.consents.insert_one(
            stamp(
                {
                    "user_id": user_id,
                    # Namespaced so a memory withdrawal can never be mistaken
                    # for — or overwrite — an onboarding consent of the same name.
                    "type": f"memory.{memory_type.value}",
                    "granted_at": granted_at,
                    "revoked_at": moment,
                    "surface": surface,
                },
                now=moment,
            )
        )

    async def delete_all_for_user(self, user_id: ObjectId) -> int:
        """§13 user rights: deletion removes application records, embeddings
        included. Called by the account-deletion orchestration."""
        result = await self._db.memories.delete_many({"user_id": user_id})
        return int(result.deleted_count)

    async def sourced_from_messages(
        self, *, user_id: ObjectId, message_ids: Sequence[ObjectId]
    ) -> list[Memory]:
        """The rows a scoped deletion is about to touch.

        Read before the delete, so the withdrawal ledger can record what type
        each memory was. After the delete there is nothing left to ask.
        """
        if not message_ids:
            return []
        cursor = self._db.memories.find(
            {"user_id": user_id, "source_message_id": {"$in": list(message_ids)}}
        )
        return [Memory.from_doc(doc) async for doc in cursor]

    async def delete_sourced_from_messages(
        self, *, user_id: ObjectId, message_ids: Sequence[ObjectId]
    ) -> int:
        """The opt-in half of §30.5's journal-deletion checkbox.

        "delete a journal entry → artefact removed (memories sourced from it
        survive unless also deleted — offered as a checkbox)". This is the box
        being ticked; leaving it unticked simply never calls this.
        """
        if not message_ids:
            return 0
        result = await self._db.memories.delete_many(
            {"user_id": user_id, "source_message_id": {"$in": list(message_ids)}}
        )
        return int(result.deleted_count)

    async def mark_source_removed(
        self, *, user_id: ObjectId, message_ids: Sequence[ObjectId]
    ) -> int:
        """§30.5: "delete a conversation → … dependent memory sources marked
        'source removed'".

        The memory survives — the user consented to Tara knowing it, and that
        consent did not expire with the thread it came from. What is lost is
        the ability to jump back to the turn, and the vault says so.
        """
        if not message_ids:
            return 0
        result = await self._db.memories.update_many(
            {"user_id": user_id, "source_message_id": {"$in": list(message_ids)}},
            {
                "$set": {
                    "visibility.source_state": SourceState.REMOVED.value,
                    "source_message_id": None,
                    "updated_at": dt.datetime.now(dt.UTC),
                }
            },
        )
        return int(result.modified_count)
