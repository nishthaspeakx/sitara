"""Daily-guidance test harness.

Two kinds of test live here and they use different fixtures on purpose.

The §7.1 scheduling arithmetic, the ranking engine and the composer are PURE —
no database, no model — so they are tested against plain values. That is the
whole reason those modules were written without I/O: a DST boundary at the date
line is a hard case to reason about and a trivial one to reproduce.

The stores are tested against the REAL Mongo from the compose stack on 27018,
against the real §6.4 validators. Root CLAUDE.md records why: an in-memory fake
once took string ids where §6.4 requires objectId, so every real write failed
validation while the whole suite stayed green.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from sitara_schemas.facts import (
    DayTimingKind,
    DayTimingValue,
    FactKind,
    FactMethod,
    FactPrecision,
    FactSnapshot,
    Graha,
    HouseAssignmentValue,
    MoolankValue,
    Nakshatra,
    NakshatraBoundaryValue,
    Paksha,
    TimingQuality,
    TithiBoundaryValue,
    TzMethod,
    build_fact_id,
)

from sitara_api.daily_guidance.types import BriefSubject, Density, Tier
from sitara_api.db import ensure_indexes

MONGO_URI = "mongodb://localhost:27018"  # compose mongo — NEVER machine-local

IST = TzMethod(tz="Asia/Kolkata", utc_offset_seconds=19800)
USER_ID = "6a70000000000000000000a1"
LOCAL_DATE = "2026-08-12"

#: 2026-08-12, IST. Every fact below is valid across this local day.
DAY_START = dt.datetime(2026, 8, 11, 18, 30, tzinfo=dt.UTC)  # 00:00 IST
DAY_END = dt.datetime(2026, 8, 12, 18, 29, tzinfo=dt.UTC)


def _snapshot(kind: FactKind, value, kind_path: str, scope: str = LOCAL_DATE) -> FactSnapshot:  # noqa: ANN001
    return FactSnapshot(
        fact_id=build_fact_id(kind_path, scope, USER_ID, 1),
        kind=kind,
        value=value,
        precision=FactPrecision(tolerance=0, unit="exact"),
        method=FactMethod(ayanamsa="lahiri", tz=IST, rise_set="upper_limb_refracted"),
        valid_from=DAY_START,
        valid_to=DAY_END,
        engine_semver="0.1.0",
        data_revision="test",
    )


@pytest.fixture()
def tithi_fact() -> FactSnapshot:
    return _snapshot(
        FactKind.PANCHANG_TITHI_BOUNDARY,
        TithiBoundaryValue(
            starts_utc=DAY_START,
            ends_utc=DAY_END,
            tithi_index=5,
            paksha=Paksha.SHUKLA,
        ),
        "panchang.tithi.boundary",
    )


@pytest.fixture()
def nakshatra_fact() -> FactSnapshot:
    return _snapshot(
        FactKind.PANCHANG_NAKSHATRA_BOUNDARY,
        NakshatraBoundaryValue(
            starts_utc=DAY_START,
            ends_utc=DAY_END,
            nakshatra=Nakshatra.ROHINI,
            nakshatra_index=4,
        ),
        "panchang.nakshatra.boundary",
    )


@pytest.fixture()
def rahu_kaal_fact() -> FactSnapshot:
    """09:00–10:30 IST on the local day — an inauspicious window."""
    return _snapshot(
        FactKind.PANCHANG_DAY_TIMING,
        DayTimingValue(
            starts_utc=dt.datetime(2026, 8, 12, 3, 30, tzinfo=dt.UTC),
            ends_utc=dt.datetime(2026, 8, 12, 5, 0, tzinfo=dt.UTC),
            timing=DayTimingKind.RAHU_KAAL,
            quality=TimingQuality.INAUSPICIOUS,
        ),
        "panchang.day_timing",
    )


@pytest.fixture()
def abhijit_fact() -> FactSnapshot:
    """11:48–12:36 IST — the auspicious window."""
    return _snapshot(
        FactKind.PANCHANG_DAY_TIMING,
        DayTimingValue(
            starts_utc=dt.datetime(2026, 8, 12, 6, 18, tzinfo=dt.UTC),
            ends_utc=dt.datetime(2026, 8, 12, 7, 6, tzinfo=dt.UTC),
            timing=DayTimingKind.ABHIJIT,
            quality=TimingQuality.AUSPICIOUS,
        ),
        "panchang.day_timing",
    )


@pytest.fixture()
def saturn_house_fact() -> FactSnapshot:
    return _snapshot(
        FactKind.TRANSIT_GRAHA_HOUSE,
        HouseAssignmentValue(graha=Graha.SATURN, whole_sign_house=10, bhava=10),
        "transit.saturn.house",
    )


@pytest.fixture()
def moolank_fact() -> FactSnapshot:
    return _snapshot(
        FactKind.NUMEROLOGY_MOOLANK,
        MoolankValue(value=7, birth_day=16, reduction_steps=(16, 7)),
        "numerology.moolank",
        scope="natal",
    )


@pytest.fixture()
def full_facts(  # noqa: PLR0913
    tithi_fact,
    nakshatra_fact,
    rahu_kaal_fact,
    abhijit_fact,
    saturn_house_fact,
    moolank_fact,
) -> tuple[FactSnapshot, ...]:
    """Enough for every fact-bearing module at every density."""
    return (
        tithi_fact,
        nakshatra_fact,
        rahu_kaal_fact,
        abhijit_fact,
        saturn_house_fact,
        moolank_fact,
    )


def subject(
    *,
    user_id: str = USER_ID,
    locale: str = "en",
    timezone: str = "Asia/Kolkata",
    brief_time: str = "07:00",
    density: Density = Density.MED,
    tier: Tier = Tier.PAYING,
    follow_timezone: bool = True,
) -> BriefSubject:
    return BriefSubject(
        user_id=user_id,
        locale=locale,
        timezone=timezone,
        brief_time=brief_time,
        density=density,
        tier=tier,
        follow_timezone=follow_timezone,
        lat=19.076,
        lon=72.877,
    )


@pytest_asyncio.fixture()
async def db() -> AsyncIterator:
    client: AsyncIOMotorClient = AsyncIOMotorClient(MONGO_URI, tz_aware=True)
    name = f"sitara_test_{uuid.uuid4().hex[:8]}"
    database = client[name]
    await ensure_indexes(database)
    yield database
    await client.drop_database(name)
    client.close()


@pytest.fixture()
def user_oid() -> ObjectId:
    return ObjectId(USER_ID)


__all__ = ["LOCAL_DATE", "MONGO_URI", "USER_ID", "subject"]
