"""`family_members` (§6.4) and the records a member's deletion reaches.

§32.15's deletion crosses three collections — `family_members`,
`birth_details`, `charts` — and touches a fourth, `consents`, which it
deliberately does NOT clear. Each of those is a separate method here rather
than one `delete_everything`, because "everything" is exactly the word §32.15
spends a sentence correcting.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from bson import ObjectId
from pymongo import ASCENDING

from sitara_api.db.documents import stamp
from sitara_api.family.models import FamilyMember, MemorialState, Relation

logger = logging.getLogger(__name__)

#: §13's attestation, in the §6.4 `consents` ledger. Namespaced so it can
#: never be confused with an onboarding consent or a CC-011 memory withdrawal.
ATTESTATION_CONSENT_TYPE = "family.attestation"

#: §29.1's S27/S28 — the surface an attestation was given on.
ATTESTATION_SURFACE = "S28"


class FamilyStore:
    def __init__(self, db: Any) -> None:
        self._db = db

    # -- read ---------------------------------------------------------------

    async def list_members(self, owner_user_id: ObjectId) -> list[FamilyMember]:
        cursor = self._db.family_members.find({"owner_user_id": owner_user_id}).sort(
            "created_at", ASCENDING
        )
        return [FamilyMember.from_doc(doc) async for doc in cursor]

    async def get(self, owner_user_id: ObjectId, member_id: ObjectId) -> FamilyMember | None:
        doc = await self._db.family_members.find_one(
            {"_id": member_id, "owner_user_id": owner_user_id}
        )
        return FamilyMember.from_doc(doc) if doc else None

    # -- write --------------------------------------------------------------

    async def create(
        self,
        *,
        owner_user_id: ObjectId,
        relation: Relation,
        name: str,
        language_tag: str = "en",
        now: dt.datetime | None = None,
    ) -> FamilyMember:
        document = stamp(
            {
                "owner_user_id": owner_user_id,
                "relation": relation.value,
                "name": name,
                "language_tag": language_tag,
                "has_birth_details": False,
                "attested_at": None,
                # §45's default, written at creation rather than left absent —
                # a field that is sometimes missing is a field every reader
                # has to defend against.
                "memorial_state": MemorialState.LIVING.value,
            },
            now=now,
        )
        result = await self._db.family_members.insert_one(document)
        document["_id"] = result.inserted_id
        return FamilyMember.from_doc(document)

    async def update(
        self,
        *,
        owner_user_id: ObjectId,
        member_id: ObjectId,
        relation: Relation | None = None,
        name: str | None = None,
        language_tag: str | None = None,
        now: dt.datetime | None = None,
    ) -> FamilyMember | None:
        changes: dict[str, Any] = {"updated_at": now or dt.datetime.now(dt.UTC)}
        if relation is not None:
            changes["relation"] = relation.value
        if name is not None:
            changes["name"] = name
        if language_tag is not None:
            changes["language_tag"] = language_tag

        doc = await self._db.family_members.find_one_and_update(
            {"_id": member_id, "owner_user_id": owner_user_id},
            {"$set": changes},
            return_document=True,
        )
        return FamilyMember.from_doc(doc) if doc else None

    async def set_attested(
        self,
        *,
        owner_user_id: ObjectId,
        member_id: ObjectId,
        now: dt.datetime | None = None,
    ) -> FamilyMember | None:
        """§13's attestation checkbox, stamped on the member AND appended to
        the §6.4 consent ledger.

        Both, not either: the member's `attested_at` is what the birth-details
        path checks on every write, and the ledger row is the permanent record
        §32.15 keeps after the member is gone.
        """
        moment = now or dt.datetime.now(dt.UTC)
        doc = await self._db.family_members.find_one_and_update(
            {"_id": member_id, "owner_user_id": owner_user_id},
            {"$set": {"attested_at": moment, "updated_at": moment}},
            return_document=True,
        )
        if doc is None:
            return None

        await self._db.consents.insert_one(
            stamp(
                {
                    "user_id": owner_user_id,
                    # No member id and no name: §32.15 keeps the RECORD and not
                    # the data, and a ledger row naming a deleted person would
                    # be the data surviving under another heading.
                    "type": ATTESTATION_CONSENT_TYPE,
                    "granted_at": moment,
                    "revoked_at": None,
                    "surface": ATTESTATION_SURFACE,
                },
                now=moment,
            )
        )
        return FamilyMember.from_doc(doc)

    async def set_memorial_state(
        self,
        *,
        owner_user_id: ObjectId,
        member_id: ObjectId,
        state: MemorialState,
        now: dt.datetime | None = None,
    ) -> FamilyMember | None:
        """§45's conversion — and the whole point is what it does NOT write.

        One `$set`, one field (plus the `updated_at` every §6.4 document
        carries). No cascade, no other collection, no cleanup pass. The
        person who chose this over §32.15's deletion chose it because she did
        not want anything destroyed, and the way to keep that promise is for
        there to be no code here that could break it.
        """
        moment = now or dt.datetime.now(dt.UTC)
        doc = await self._db.family_members.find_one_and_update(
            {"_id": member_id, "owner_user_id": owner_user_id},
            {"$set": {"memorial_state": state.value, "updated_at": moment}},
            return_document=True,
        )
        return FamilyMember.from_doc(doc) if doc else None

    async def living_members(self, owner_user_id: ObjectId) -> list[FamilyMember]:
        """§45.2: those a forward-looking reminder may be about (§23.2).

        A QUERY, never a deletion. The memorial member is still in
        `list_members`, still charted, still in every past artefact — she is
        simply not the subject of "her birthday is on Sunday" three days after
        her funeral.
        """
        cursor = self._db.family_members.find(
            {
                "owner_user_id": owner_user_id,
                "memorial_state": {"$ne": MemorialState.IN_MEMORY.value},
            }
        ).sort("created_at", ASCENDING)
        return [FamilyMember.from_doc(doc) async for doc in cursor]

    async def set_has_birth_details(
        self, *, owner_user_id: ObjectId, member_id: ObjectId, value: bool
    ) -> None:
        await self._db.family_members.update_one(
            {"_id": member_id, "owner_user_id": owner_user_id},
            {"$set": {"has_birth_details": value, "updated_at": dt.datetime.now(dt.UTC)}},
        )

    # -- delete (§32.15) ----------------------------------------------------

    async def delete_member(self, *, owner_user_id: ObjectId, member_id: ObjectId) -> bool:
        result = await self._db.family_members.delete_one(
            {"_id": member_id, "owner_user_id": owner_user_id}
        )
        return result.deleted_count == 1

    async def delete_birth_details(self, member_id: ObjectId) -> int:
        """§13's crown jewels, hard-deleted (§32.15)."""
        result = await self._db.birth_details.delete_many({"family_member_id": member_id})
        return int(result.deleted_count)

    async def delete_charts(self, member_id: ObjectId) -> int:
        """§6.4 keys `charts` by `subject_id`, and a family member IS a subject."""
        result = await self._db.charts.delete_many({"subject_id": member_id})
        return int(result.deleted_count)

    async def revoke_attestation(
        self, *, owner_user_id: ObjectId, now: dt.datetime | None = None
    ) -> bool:
        """Mark the attestation withdrawn WITHOUT deleting it (§32.15).

        The row is the account-holder's own legal-basis history — that she
        once asserted a right to enter someone's birth details. Deleting it
        would destroy her record of her own act, which is the opposite of what
        a deletion right is for. `revoked_at` is §6.4's field for exactly this.
        """
        moment = now or dt.datetime.now(dt.UTC)
        result = await self._db.consents.update_one(
            {
                "user_id": owner_user_id,
                "type": ATTESTATION_CONSENT_TYPE,
                "revoked_at": None,
            },
            {"$set": {"revoked_at": moment, "updated_at": moment}},
        )
        return bool(result.modified_count)


__all__ = ["ATTESTATION_CONSENT_TYPE", "ATTESTATION_SURFACE", "FamilyStore"]
