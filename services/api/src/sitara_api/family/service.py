"""Family (§29.1 S27/S28, §6.4, §13, §32.15).

Phase 1 keeps family as CONTEXT (§10-19: no family accounts, no member-facing
views). The account-holder records who matters to her, Tara pronounces their
names correctly and — where she attests to it — answers questions about their
charts.

§32.15's deletion is the delicate part and its ORDER is deliberate. See
`delete`.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Sequence

from bson import ObjectId

from sitara_api.family.models import (
    AttestationRequired,
    DeletionEffects,
    FamilyMember,
    MemoryAboutMember,
    Relation,
)
from sitara_api.family.store import FamilyStore
from sitara_api.memory.service import MemoryService

logger = logging.getLogger(__name__)


class FamilyService:
    def __init__(
        self, *, store: FamilyStore, memory_service: MemoryService | None = None
    ) -> None:
        self._store = store
        #: §32.15's checkbox reaches `memories`. Optional so family still works
        #: where memory is unavailable — the checkbox is then not offered,
        #: rather than offered and silently ineffective.
        self._memory = memory_service

    # -- read ---------------------------------------------------------------

    async def list_members(self, owner_user_id: ObjectId) -> list[FamilyMember]:
        return await self._store.list_members(owner_user_id)

    async def get(self, owner_user_id: ObjectId, member_id: ObjectId) -> FamilyMember | None:
        return await self._store.get(owner_user_id, member_id)

    # -- write --------------------------------------------------------------

    async def add(
        self,
        *,
        owner_user_id: ObjectId,
        relation: Relation,
        name: str,
        language_tag: str = "en",
        now: dt.datetime | None = None,
    ) -> FamilyMember:
        return await self._store.create(
            owner_user_id=owner_user_id,
            relation=relation,
            name=name,
            language_tag=language_tag,
            now=now,
        )

    async def edit(
        self,
        *,
        owner_user_id: ObjectId,
        member_id: ObjectId,
        relation: Relation | None = None,
        name: str | None = None,
        language_tag: str | None = None,
        now: dt.datetime | None = None,
    ) -> FamilyMember | None:
        return await self._store.update(
            owner_user_id=owner_user_id,
            member_id=member_id,
            relation=relation,
            name=name,
            language_tag=language_tag,
            now=now,
        )

    async def attest_birth_details(
        self, *, owner_user_id: ObjectId, member_id: ObjectId, now: dt.datetime | None = None
    ) -> FamilyMember | None:
        """§13: "adding a family member's birth details requires an attestation
        checkbox"."""
        return await self._store.set_attested(
            owner_user_id=owner_user_id, member_id=member_id, now=now
        )

    async def require_attestation(
        self, *, owner_user_id: ObjectId, member_id: ObjectId
    ) -> FamilyMember:
        """The guard the birth-details write goes through.

        A method rather than an `if`, so there is one place that decides, and
        `AttestationRequired` rather than a bool, so a caller cannot proceed by
        ignoring a return value.
        """
        member = await self._store.get(owner_user_id, member_id)
        if member is None:
            raise AttestationRequired("no such family member")
        if member.attested_at is None:
            raise AttestationRequired(
                "§13 requires the account-holder's attestation before a family "
                "member's birth details may be stored"
            )
        return member

    # -- §32.15 -------------------------------------------------------------

    async def memories_about(
        self, *, owner_user_id: ObjectId, member_id: ObjectId
    ) -> list[MemoryAboutMember]:
        """§32.15's "listed" — the candidates, before anything is deleted.

        `memories` has no family-member field in §6.4, so "about them" is a
        NAME MATCH and nothing more. That is a judgement, and it is shown to
        the user precisely because it is one: a name-matched delete performed
        silently would take "Sudha's birthday is 11 March" along with a
        stranger's remark that happened to contain the word.
        """
        if self._memory is None:
            return []
        member = await self._store.get(owner_user_id, member_id)
        if member is None or not member.name:
            return []

        needle = member.name.casefold()
        candidates: list[MemoryAboutMember] = []
        for memory in await self._memory.vault(owner_user_id):
            if needle in memory.content.casefold():
                candidates.append(
                    MemoryAboutMember(
                        memory_id=memory.memory_id,
                        type=memory.type.value,
                        content=memory.content,
                    )
                )
        return candidates

    async def delete(
        self,
        *,
        owner_user_id: ObjectId,
        member_id: ObjectId,
        delete_memory_ids: Sequence[ObjectId] = (),
        now: dt.datetime | None = None,
    ) -> DeletionEffects:
        """§32.15, in an order chosen rather than stumbled into.

        1. **Ownership first.** Everything below is destructive and scoped by
           the member; a member that is not hers stops here, having touched
           nothing.
        2. **Birth details and charts**, hard-deleted — §13's crown jewels and
           the facts derived from them. Before the member row, so a failure
           mid-way leaves a member pointing at nothing rather than orphaned
           birth details pointing at nobody. Orphaned crown jewels are the
           worse of the two.
        3. **The ticked memories**, each writing its CC-011 §44.5 withdrawal.
           Scoped through the memory service's own per-user delete, so an id
           from another account is simply not found.
        4. **The member row**, which is what removes them from reminders and
           rankings — §28.2's `family_reminder` reads this collection, so
           "immediately" needs no cache to expire.
        5. **The attestation is REVOKED, never deleted** — §32.15's DPDP
           clause. Last, because it is the record that the rest happened.

        Past journal text is not in this list, and its absence is the point:
        §32.15 keeps it, and what Tara wrote last March was true when she
        wrote it.
        """
        member = await self._store.get(owner_user_id, member_id)
        if member is None:
            return DeletionEffects()

        birth_details = await self._store.delete_birth_details(member_id)
        charts = await self._store.delete_charts(member_id)

        memories = 0
        if delete_memory_ids and self._memory is not None:
            for memory_id in delete_memory_ids:
                if await self._memory.forget(
                    user_id=owner_user_id, memory_id=memory_id, now=now
                ):
                    memories += 1
        elif delete_memory_ids and self._memory is None:  # pragma: no cover - wiring guard
            logger.error(
                "family deletion asked to delete memories with no memory service "
                "wired — the checkbox was offered and could not be honoured"
            )

        removed = await self._store.delete_member(
            owner_user_id=owner_user_id, member_id=member_id
        )
        attestation_retained = False
        if member.attested_at is not None:
            await self._store.revoke_attestation(owner_user_id=owner_user_id, now=now)
            attestation_retained = True

        return DeletionEffects(
            birth_details=birth_details,
            charts=charts,
            memories=memories,
            member_removed=removed,
            attestation_retained=attestation_retained,
        )


__all__ = ["FamilyService"]
