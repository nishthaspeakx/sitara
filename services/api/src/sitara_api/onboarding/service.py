"""Persistence for the §24.4 onboarding stack.

§24.4 requires "state persisted per step (resume on return)", which is why each
screen commits as it is answered rather than the stack posting once at the end:
a user who closes the app at S09 must come back to S09, and an answer that only
exists in a client store is an answer a reinstall loses.

**What resume DOES NOT return.** `state()` reports that birth details exist and
which of §10-6's four accuracies was chosen — never the date, the time or the
place. §6.4 marks the whole `birth_details` payload encrypted and reachable
"only through the astrology facade, no generic query path"; a resume endpoint
that echoed those values back would be that generic path, reachable with nothing
but a session cookie. The accuracy is a category, not a birth detail, and S13
needs it to pick the right §5.4 confidence state.

The cost is that back-navigating to S06 on a NEW device shows an empty form
rather than a pre-filled one. That is the right side to err on: re-typing a
birth date is an inconvenience, and a generic read path for the crown jewels is
a §13 finding.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from bson import ObjectId
from sitara_schemas import ErrorCode

from sitara_api.astrology.service import AstrologyFacade, BirthDetailsInput
from sitara_api.db.documents import stamp, utcnow
from sitara_api.errors import ApiError
from sitara_api.onboarding.types import FIRST_STEP, OnboardingStep

logger = logging.getLogger(__name__)

#: §10-8's three registers → §28.2's three density modes. The mapping is here
#: rather than on the client because `profiles.density` is what §7.1 schedules
#: from: a client that sent its own value could put a string the ranking engine
#: does not know into the row that decides how many cards a morning has.
DENSITY_BY_INTEREST = {"curious": "low", "balanced": "med", "devout": "high"}

#: §24.4 S11 — "≤3 chips". Enforced server-side because it is a product rule,
#: not a form nicety: the ranking engine weights every priority it is given.
MAX_PRIORITIES = 3

#: The eight §2.2 locales. A locale outside this set is refused rather than
#: stored — §2.4 admits a language only through the §12 gate, and a profile
#: carrying an unreleased locale would ask the catalogs for strings nobody has
#: written.
LAUNCH_LOCALES = ("en", "hi", "hi-Latn")


@dataclass(frozen=True)
class OnboardingState:
    """What a resuming client is told. Deliberately small — see the module docstring."""

    locale: str
    completed_steps: tuple[int, ...] = ()
    has_birth_details: bool = False
    #: One of §10-6's four, or None before S07.
    time_accuracy: str | None = None
    has_city: bool = False
    interest: str | None = None
    priorities: tuple[str, ...] = ()
    display_name: str | None = None
    brief_time: str | None = None
    voice_enabled: bool = True

    @property
    def next_step(self) -> int:
        """The lowest step not yet answered — the stack is linear (§28.1)."""
        done = set(self.completed_steps)
        for step in OnboardingStep:
            if step.value not in done:
                return step.value
        return OnboardingStep.READING.value


@dataclass
class StepAnswers:
    """A partial update. Every field is optional because each screen sends only
    its own answer — a PATCH that required the whole object would make S09
    capable of clobbering S06."""

    locale: str | None = None
    interest: str | None = None
    priorities: list[str] | None = None
    display_name: str | None = None
    latin_name: str | None = None
    city: dict | None = None
    brief_time: str | None = None
    voice_enabled: bool | None = None
    completed_step: int | None = None
    consents: list[str] = field(default_factory=list)


class OnboardingService:
    def __init__(self, db, facade: AstrologyFacade | None = None) -> None:  # noqa: ANN001
        self._db = db
        self._facade = facade

    # -- read ---------------------------------------------------------------

    async def state(self, user_id: ObjectId) -> OnboardingState:
        profile = await self._db.profiles.find_one({"user_id": user_id}) or {}
        user = await self._db.users.find_one({"_id": user_id}) or {}
        birth = await self._db.birth_details.find_one(
            {"user_id": user_id, "family_member_id": None},
            # Projection is belt-and-braces beside the docstring's rule: even a
            # future bug that returned this document wholesale could not leak a
            # birth date, because the date was never read.
            {"time_accuracy": 1},
        )

        onboarding = profile.get("onboarding") or {}
        time_accuracy = None
        if birth is not None:
            raw = birth.get("time_accuracy")
            # CSFLE leaves this a ciphertext blob when the codec is absent; a
            # category we cannot read is a category we do not report.
            time_accuracy = raw if isinstance(raw, str) else None

        return OnboardingState(
            locale=user.get("locale") or "en",
            completed_steps=tuple(sorted(onboarding.get("completed_steps") or ())),
            has_birth_details=birth is not None,
            time_accuracy=time_accuracy,
            has_city=bool(profile.get("brief_place")),
            interest=onboarding.get("interest"),
            priorities=tuple(profile.get("priorities") or ()),
            display_name=(profile.get("name_pronunciation") or {}).get("display_name"),
            brief_time=profile.get("brief_time"),
            voice_enabled=bool(onboarding.get("voice_enabled", True)),
        )

    # -- write --------------------------------------------------------------

    async def apply(self, user_id: ObjectId, answers: StepAnswers) -> OnboardingState:
        """Apply one screen's answer. Idempotent — a retried PATCH is a no-op."""
        profile_set: dict = {}
        profile_add: dict = {}

        if answers.locale is not None:
            if answers.locale not in LAUNCH_LOCALES:
                raise ApiError(ErrorCode.SYS_VALIDATION)
            await self._db.users.update_one(
                {"_id": user_id},
                {"$set": {"locale": answers.locale, "updated_at": utcnow()}},
            )

        if answers.interest is not None:
            density = DENSITY_BY_INTEREST.get(answers.interest)
            if density is None:
                raise ApiError(ErrorCode.SYS_VALIDATION)
            profile_set["density"] = density
            profile_set["onboarding.interest"] = answers.interest

        if answers.priorities is not None:
            if len(answers.priorities) > MAX_PRIORITIES:
                raise ApiError(ErrorCode.SYS_VALIDATION)
            profile_set["priorities"] = list(answers.priorities)

        if answers.display_name is not None:
            # §22.10: the CONFIRMED Latin form is the canonical numerology
            # input, so both are stored — the name as she writes it, and the
            # spelling the Chaldean table is read against. Storing only one
            # would either lose her script or re-transliterate on every read.
            profile_set["name_pronunciation.display_name"] = answers.display_name
            if answers.latin_name is not None:
                profile_set["name_pronunciation.latin"] = answers.latin_name
                profile_set["name_pronunciation.confirmed_at"] = utcnow()

        if answers.city is not None:
            profile_set["brief_place"] = answers.city

        if answers.brief_time is not None:
            # §7.1's index does a STRING range scan over this field, so the
            # zero-padding is load-bearing: "7:00" sorts after "10:00".
            if not _is_hhmm(answers.brief_time):
                raise ApiError(ErrorCode.SYS_VALIDATION)
            profile_set["brief_time"] = answers.brief_time

        if answers.voice_enabled is not None:
            profile_set["onboarding.voice_enabled"] = answers.voice_enabled

        if answers.completed_step is not None:
            try:
                step = OnboardingStep(answers.completed_step)
            except ValueError:
                raise ApiError(ErrorCode.SYS_VALIDATION) from None
            profile_add["onboarding.completed_steps"] = step.value

        if profile_set or profile_add:
            update: dict = {"$setOnInsert": stamp({"user_id": user_id})}
            update["$setOnInsert"].pop("updated_at", None)
            if profile_set:
                update["$set"] = {**profile_set, "updated_at": utcnow()}
            else:
                update["$set"] = {"updated_at": utcnow()}
            if profile_add:
                update["$addToSet"] = profile_add
            await self._db.profiles.update_one({"user_id": user_id}, update, upsert=True)

        for consent_type in answers.consents:
            await self.record_consent(user_id, consent_type)

        return await self.state(user_id)

    async def record_consent(self, user_id: ObjectId, consent_type: str, *, surface: str = "S05") -> None:
        """Append to the §13 consent ledger.

        Upsert on (user_id, type) rather than insert: a user who backs into S05
        and continues again has not consented twice, and a ledger that says she
        did is a worse record than one that says when she first did.
        """
        await self._db.consents.update_one(
            {"user_id": user_id, "type": consent_type},
            {
                "$set": {"surface": surface, "revoked_at": None, "updated_at": utcnow()},
                "$setOnInsert": stamp(
                    {
                        "user_id": user_id,
                        "type": consent_type,
                        "granted_at": utcnow(),
                    }
                ),
            },
            upsert=True,
        )

    async def set_birth(self, user_id: ObjectId, details: BirthDetailsInput) -> None:
        """S06 + S07, written through §13's single door and nowhere else."""
        if self._facade is None:
            # Without the facade there is no encrypted write path, and writing
            # a birth row in the clear is not a degraded mode — it is the one
            # thing §13 does not permit. Refuse, retryably.
            raise ApiError(ErrorCode.SYS_UNAVAILABLE)
        await self._facade.set_birth_details(str(user_id), details)


def _is_hhmm(value: str) -> bool:
    if len(value) != 5 or value[2] != ":":
        return False
    hh, mm = value[:2], value[3:]
    return hh.isdigit() and mm.isdigit() and 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59


__all__ = [
    "DENSITY_BY_INTEREST",
    "FIRST_STEP",
    "MAX_PRIORITIES",
    "OnboardingService",
    "OnboardingState",
    "StepAnswers",
]
