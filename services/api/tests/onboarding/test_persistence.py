"""The onboarding writes, against the REAL collections and their validators.

Every defect this file covers shipped green. `test_reading.py` exercises the
composer, which is pure; the flow suite drives a stub that answers success. So
nothing in M8 ever asked MongoDB whether these documents were acceptable, and
two of them were not:

* `record_consent` named `updated_at` in both `$set` and `$setOnInsert`, which
  Mongo rejects outright — the §13 ledger recorded nothing and S05 returned a
  500 for every user.
* the S13 audit row omitted `guidance_logs`' required `date` and put the
  snapshots in `facts` where §6.4 declares `fact_snapshots`, so the insert was
  rejected and the `except` swallowed it. §34.2's record of the reading did not
  exist.

CLAUDE.md's rule names this shape exactly: "a fake that accepts what the real
system rejects is a defect in the fake". These tests are the real system.
"""

from __future__ import annotations

import datetime as dt

import pytest
import pytest_asyncio
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from sitara_api.db import ensure_indexes
from sitara_api.db.documents import stamp
from sitara_api.onboarding.service import OnboardingService, StepAnswers

MONGO_URI = "mongodb://localhost:27018"  # compose mongo — NEVER machine-local
USER_ID = ObjectId("6a70000000000000000000b7")

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture()
async def db():
    client = AsyncIOMotorClient(MONGO_URI, tz_aware=True, serverSelectionTimeoutMS=2000)
    database = client["sitara_test_onboarding"]
    await ensure_indexes(database)
    yield database
    for name in ("profiles", "consents", "users", "guidance_logs"):
        await database[name].delete_many({})
    client.close()


# ---------------------------------------------------------------------------
# §13's consent ledger
# ---------------------------------------------------------------------------


async def test_a_consent_is_actually_recorded(db) -> None:  # noqa: ANN001
    """The write that failed on every call. Permanent, legal, and it stored nothing."""
    await OnboardingService(db).record_consent(USER_ID, "essential")

    row = await db.consents.find_one({"user_id": USER_ID, "type": "essential"})
    assert row is not None, "§13's ledger recorded nothing"
    assert row["granted_at"] is not None
    assert row["revoked_at"] is None
    assert row["surface"] == "S05"


async def test_re_consenting_does_not_record_a_second_grant(db) -> None:  # noqa: ANN001
    """A user who backs into S05 and continues again has not consented twice."""
    service = OnboardingService(db)
    await service.record_consent(USER_ID, "essential")
    first = await db.consents.find_one({"user_id": USER_ID, "type": "essential"})
    await service.record_consent(USER_ID, "essential")

    assert await db.consents.count_documents({"user_id": USER_ID, "type": "essential"}) == 1
    again = await db.consents.find_one({"user_id": USER_ID, "type": "essential"})
    # The original grant instant survives — that is what the ledger is FOR.
    assert again["granted_at"] == first["granted_at"]


# ---------------------------------------------------------------------------
# §24.4's per-step persistence
# ---------------------------------------------------------------------------


async def test_each_step_persists_and_resume_advances(db) -> None:  # noqa: ANN001
    service = OnboardingService(db)
    await service.apply(USER_ID, StepAnswers(locale="hi", completed_step=2))
    await service.apply(USER_ID, StepAnswers(interest="devout", completed_step=9))

    state = await service.state(USER_ID)
    assert state.completed_steps == (2, 9)
    assert state.interest == "devout"
    # §10-8 → §28.2: the register picks the density, and the client never sends it.
    assert (await db.profiles.find_one({"user_id": USER_ID}))["density"] == "high"
    # The stack is linear, so "next" is the lowest UNrecorded step (§28.1).
    assert state.next_step == 3


async def test_a_retried_patch_is_a_no_op(db) -> None:  # noqa: ANN001
    service = OnboardingService(db)
    for _ in range(3):
        await service.apply(USER_ID, StepAnswers(completed_step=5))
    profile = await db.profiles.find_one({"user_id": USER_ID})
    assert profile["onboarding"]["completed_steps"] == [5]


async def test_resume_never_returns_a_birth_detail(db) -> None:  # noqa: ANN001
    """§6.4: `birth_details` is reachable only through the astrology facade.

    A resume endpoint that echoed the values back would be the generic read path
    §13 forbids, reachable with nothing but a session cookie.
    """
    await db.birth_details.insert_one(
        stamp(
            {
                "user_id": USER_ID,
                "family_member_id": None,
                "date": "1994-03-17",
                "time": "06:45:00",
                "time_accuracy": "exact",
                "place": {"label": "Bengaluru", "lat": 12.97, "lon": 77.59, "tz": "Asia/Kolkata"},
                "tz_snapshot": {"tz": "Asia/Kolkata"},
                "rectification_notes": None,
            }
        )
    )
    state = await OnboardingService(db).state(USER_ID)

    assert state.has_birth_details is True
    # The accuracy is a CATEGORY, and §5.4 needs it to pick a confidence state.
    assert state.time_accuracy == "exact"
    # Nothing else about the birth row may appear on this object.
    leaked = {"1994-03-17", "06:45:00", "Bengaluru", 12.97, 77.59}
    assert not (set(map(str, vars(state).values())) & set(map(str, leaked)))
    await db.birth_details.delete_many({"user_id": USER_ID})


async def test_an_unreleased_locale_is_refused(db) -> None:  # noqa: ANN001
    """§2.4 admits a language only through the §12 gate. A profile carrying one
    nobody has translated asks the catalogs for strings that do not exist."""
    from sitara_api.errors import ApiError

    with pytest.raises(ApiError):
        await OnboardingService(db).apply(USER_ID, StepAnswers(locale="ta"))


async def test_more_than_three_priorities_is_refused(db) -> None:  # noqa: ANN001
    """§24.4 S11's cap is a product rule — the ranking engine weights every
    priority it is given — so it is enforced here, not only in the interface."""
    from sitara_api.errors import ApiError

    with pytest.raises(ApiError):
        await OnboardingService(db).apply(
            USER_ID, StepAnswers(priorities=["career", "family", "health", "money"])
        )


# ---------------------------------------------------------------------------
# §34.2's artefact record
# ---------------------------------------------------------------------------


async def test_the_first_reading_audit_row_is_accepted_by_its_validator(db) -> None:  # noqa: ANN001
    """The row S13 writes, against `guidance_logs`' real §6.4 validator.

    It was rejected for a missing `date` and the snapshots went to `facts`
    instead of `fact_snapshots` — and the write is best-effort, so it failed in
    silence. "Which reading did she actually see?" had no answer at all.
    """
    await db.guidance_logs.insert_one(
        stamp(
            {
                "user_id": USER_ID,
                "date": dt.datetime.now(dt.UTC).date().isoformat(),
                "confidence": "verified",
                "fact_ids": ["fact:natal.moon.nakshatra/natal/x@v1"],
                "fact_snapshots": [{"fact_id": "fact:natal.moon.nakshatra/natal/x@v1"}],
                "template_ids": ["moon_nakshatra", "observation", "panchang"],
                "why": {
                    "surface": "first_reading",
                    "status": "complete",
                    "source_state": "default",
                    "degrade_reason": None,
                },
            }
        )
    )
    row = await db.guidance_logs.find_one({"user_id": USER_ID})
    assert row is not None
    # §34.2: the snapshot is EMBEDDED, under the name §6.4 declares — anything
    # reading the declared field must find it there.
    assert row["fact_snapshots"], "the cited snapshots are not where §6.4 says"
    assert row["why"]["surface"] == "first_reading"
