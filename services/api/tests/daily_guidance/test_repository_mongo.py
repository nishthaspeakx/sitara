"""The two subject loaders, against real Mongo — and the rule that they agree.

There are two paths from a stored profile to a `BriefSubject`:

    SubjectRepository.candidates()   the 15-minute tick's bulk aggregation
    wiring.load_subject()            the per-user task, and every regenerate

They must produce the same subject for the same user, and for a while they did
not: the tick's loader dropped `brief_place`, so every SCHEDULED brief lost its
panchang half and shipped chart-only, while the regenerate path — which goes
through `load_subject` — kept its timings. Nothing failed. The briefs were
simply thinner, in a way only a side-by-side would show.

`test_the_two_loaders_agree` is that side-by-side, and it is the point of this
file.
"""

from __future__ import annotations

import datetime as dt

import pytest
from bson import ObjectId

from sitara_api.daily_guidance.repository import SubjectRepository
from sitara_api.daily_guidance.types import Density, Tier
from sitara_api.daily_guidance.wiring import load_subject
from sitara_api.db.documents import stamp

pytestmark = pytest.mark.asyncio()

#: 03:45 UTC = 09:15 IST; a 10:00 IST brief_time is then 45 minutes ahead.
TICK = dt.datetime(2026, 8, 12, 3, 45, tzinfo=dt.UTC)
PLACE = {"lat": 19.076, "lon": 72.877, "tz": "Asia/Kolkata", "name": "Mumbai"}


async def seed(
    db,  # noqa: ANN001
    *,
    brief_time: str = "10:00",
    status: str = "active",
    plan: str = "annual",
    place: dict | None = PLACE,
    density: str = "med",
) -> ObjectId:
    user_id = ObjectId()
    await db.users.insert_one(
        stamp(
            {
                "_id": user_id,
                "firebase_uid": f"uid-{user_id}",
                "locale": "hi",
                "timezone": "Asia/Kolkata",
                "status": status,
            }
        )
    )
    profile: dict = {
        "user_id": user_id,
        "brief_time": brief_time,
        "density": density,
        "follow_timezone": True,
    }
    if place is not None:
        profile["brief_place"] = place
    await db.profiles.insert_one(stamp(profile))
    await db.subscriptions.insert_one(
        stamp(
            {
                "user_id": user_id,
                "plan": plan,
                "region": "IN",
                "provider": "razorpay",
                "status": "active",
            }
        )
    )
    return user_id


async def test_the_two_loaders_agree(db) -> None:  # noqa: ANN001
    """The regression. Two loaders, one shape — or a scheduled brief quietly
    differs from a regenerated one."""
    user_id = await seed(db)

    (from_tick,) = await SubjectRepository(db).candidates(TICK)
    from_task = await load_subject(db, str(user_id))

    assert from_task is not None
    for field in (
        "user_id",
        "locale",
        "timezone",
        "brief_time",
        "density",
        "follow_timezone",
        "lat",
        "lon",
    ):
        assert getattr(from_tick, field) == getattr(from_task, field), field


async def test_the_tick_carries_the_brief_place(db) -> None:  # noqa: ANN001
    """§7.1's panchang facts are computed FOR a place. Without it the wave's
    briefs lose their timings and nothing raises."""
    await seed(db)
    (subject,) = await SubjectRepository(db).candidates(TICK)
    assert subject.lat == PLACE["lat"]
    assert subject.lon == PLACE["lon"]


async def test_a_profile_with_no_place_still_yields_a_subject(db) -> None:  # noqa: ANN001
    """A user who has not set a city yet is scheduled and degrades on the
    panchang half — §7.1's stated path — rather than being dropped silently."""
    await seed(db, place=None)
    (subject,) = await SubjectRepository(db).candidates(TICK)
    assert subject.lat is None and subject.lon is None


async def test_the_band_query_finds_a_user_inside_the_lead_window(db) -> None:  # noqa: ANN001
    await seed(db, brief_time="10:00")  # 45 min after the 09:15 IST tick
    assert len(await SubjectRepository(db).candidates(TICK)) == 1


async def test_the_band_query_excludes_a_user_outside_it(db) -> None:  # noqa: ANN001
    """22:00 is nowhere near 30–90 minutes after 09:15 local."""
    await seed(db, brief_time="22:00")
    assert await SubjectRepository(db).candidates(TICK) == []


async def test_a_suspended_account_is_never_scheduled(db) -> None:  # noqa: ANN001
    """A soft-deleted account inside its 30-day grace (§6.4) still exists;
    restoring it must not mean explaining a fortnight of notifications."""
    await seed(db, status="deleted")
    assert await SubjectRepository(db).candidates(TICK) == []


async def test_the_tier_comes_from_the_subscription(db) -> None:  # noqa: ANN001
    await seed(db, plan="trial")
    (subject,) = await SubjectRepository(db).candidates(TICK)
    assert subject.tier is Tier.TRIAL


async def test_an_unknown_density_falls_back_to_med(db) -> None:  # noqa: ANN001
    """§28.2's default is the onboarding interest level, and MED where it was
    never captured — never HIGH, which would show a skeptic the choghadiya
    strip on their first morning."""
    await seed(db, density="enormous")
    (subject,) = await SubjectRepository(db).candidates(TICK)
    assert subject.density is Density.MED


async def test_live_timezones_are_distinct(db) -> None:  # noqa: ANN001
    await seed(db)
    await seed(db)
    assert await SubjectRepository(db).live_timezones() == ["Asia/Kolkata"]
