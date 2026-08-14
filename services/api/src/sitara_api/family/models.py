"""Family types (§6.4 `family_members`, §30.5, §32.15).

**Phase 1 has no family accounts** (§10-19). A family member is context the
account-holder keeps: a relationship, a name Tara pronounces correctly, and —
if the account-holder attests to it (§13) — birth details that let Tara answer
questions about them. There is no member-facing view, no login, no invitation.

That framing decides the deletion rules. Deleting a member is the
account-holder editing her own records, which is why §32.15 keeps the
attestation while destroying the data: the consent she gave is a fact about
her, and the birth details were a fact about someone else.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from bson import ObjectId


class Relation(StrEnum):
    """The relationship record.

    A closed set rather than free text, because the relation is read by the
    ranking engine (§28.2's `family_reminder`) and rendered through i18n keys
    — a typed relation is a label in three locales, and a typed string is an
    English word in a Hindi sentence.

    `OTHER` exists so nobody is unrepresentable; it renders as the name alone
    rather than as a guessed relationship.
    """

    PARTNER = "partner"
    MOTHER = "mother"
    FATHER = "father"
    DAUGHTER = "daughter"
    SON = "son"
    SISTER = "sister"
    BROTHER = "brother"
    GRANDMOTHER = "grandmother"
    GRANDFATHER = "grandfather"
    FRIEND = "friend"
    OTHER = "other"


# ── §32.15's "in memory of" is NOT built, and this is the record ───────────
#
# §32.15 offers "'In memory of' conversion … as the alternative on the same
# sheet". It is a STATE of a family member — the records stay, the reminders
# soften, nothing is destroyed — and §6.4's `family_members` row has no field
# to hold it: owner_user_id, relation, name, language_tag, has_birth_details,
# attested_at, and nothing else.
#
# That is the same shape as CC-011's saved guidance: a spec requirement with
# no home in a frozen table. It is deliberately NOT solved the same way here,
# because CC-011 was approved for `journal_saves` specifically and a second
# amendment to §6.4 is a second founder decision, not an implementation
# detail. Writing an undeclared field would be exactly the drift
# `sitara_api.db.verify` exists to catch.
#
# Everything else in §32.15 IS built: the hard delete of birth details and
# charts, the listed checkbox for memories, the retained attestation, and the
# immediate removal from reminders and rankings. What is missing is the
# gentler alternative to all of it, which is the half a grieving user most
# needs — so it is named here rather than left to be discovered.
MEMORIAL_STATE_IS_UNBUILT = (
    "§32.15's 'in memory of' conversion needs a `family_members` field that "
    "§6.4 does not declare; it awaits a change-control entry."
)


class AttestationRequired(ValueError):
    """§13: "adding a family member's birth details requires an attestation
    checkbox". Not a warning — birth details do not land without it."""


@dataclass(frozen=True)
class FamilyMember:
    member_id: ObjectId
    owner_user_id: ObjectId
    relation: Relation
    name: str
    language_tag: str
    has_birth_details: bool = False
    attested_at: dt.datetime | None = None
    created_at: dt.datetime | None = None

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> FamilyMember:
        name = doc.get("name")
        return cls(
            member_id=doc["_id"],
            owner_user_id=doc["owner_user_id"],
            relation=Relation(doc.get("relation", Relation.OTHER.value)),
            # A CSFLE name read without the codec comes back as Binary. It is
            # rendered as an empty name rather than as a repr of ciphertext —
            # the same rule `daily_guidance` follows when a name reads back as
            # a blob: decline rather than compose around it.
            name=name if isinstance(name, str) else "",
            language_tag=doc.get("language_tag", "en"),
            has_birth_details=bool(doc.get("has_birth_details")),
            attested_at=doc.get("attested_at"),
            created_at=doc.get("created_at"),
        )


@dataclass(frozen=True)
class MemoryAboutMember:
    """One candidate for §32.15's checkbox.

    §32.15 says "offers checkbox deletion of memories about them (default
    keep, **listed**)". Listed is the operative word: `memories` has no
    family-member field in §6.4, so "about them" is a judgement, and a
    judgement the software makes silently would delete the wrong things. The
    user sees each candidate and ticks it, or does not.
    """

    memory_id: ObjectId
    type: str
    content: str


@dataclass(frozen=True)
class DeletionEffects:
    """What a §32.15 deletion actually did, so the UI can say so afterwards."""

    birth_details: int = 0
    charts: int = 0
    memories: int = 0
    member_removed: bool = False
    attestation_retained: bool = False


__all__ = [
    "MEMORIAL_STATE_IS_UNBUILT",
    "AttestationRequired",
    "DeletionEffects",
    "FamilyMember",
    "MemoryAboutMember",
    "Relation",
]
