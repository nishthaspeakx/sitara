"""Assembling the tick's candidate subjects from Mongo.

The §7.1 selector is pure over `BriefSubject` rows; this is where those rows
come from. The interesting part is the pre-filter, because the naive query is
"every active user, every fifteen minutes" and that does not survive Stage 2.

The narrowing works backwards from the window. A user with UTC offset `O` and
local brief time `B` is due at UTC instant `B - O` on their local date, and the
tick wants everyone due in `[T+30, T+90]`. Rearranged, `B ∈ [T+30+O, T+90+O]` —
so for each distinct offset in play there is a 60-minute band of LOCAL clock
times worth loading, and `profiles.brief_time` is indexed for exactly that
range scan (the index cites §7.1 for this reason).

The bands are unioned across offsets and the result is then filtered exactly,
in Python, against each user's real IANA zone. That second pass is not
redundant: offsets are a lossy summary of a zone — they move twice a year, and
half-hour and three-quarter-hour zones make the union wider than any single
user's band. The query narrows; `windows.wave_member` decides.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Iterable, Sequence
from zoneinfo import ZoneInfo

from sitara_api.daily_guidance.priority import Entitlement, tier_for
from sitara_api.daily_guidance.types import BriefSubject, Density, Tier
from sitara_api.daily_guidance.windows import (
    DEFAULT_BRIEF_TIME,
    LEAD_MAX_MINUTES,
    LEAD_MIN_MINUTES,
    TICK_MINUTES,
)

logger = logging.getLogger(__name__)

#: Users whose account is in one of these states are not scheduled at all.
#: A soft-deleted account inside its 30-day grace (§6.4) still exists and must
#: not receive a morning brief — restoring it should not mean explaining a
#: fortnight of notifications.
SCHEDULABLE_STATUSES: frozenset[str] = frozenset({"active"})


def offset_bands(
    zones: Iterable[str], tick: dt.datetime, *, tick_minutes: int = TICK_MINUTES
) -> list[tuple[str, str]]:
    """Local-clock bands worth loading for this tick, one per distinct offset.

    Returned as ("HH:MM", "HH:MM") pairs against `profiles.brief_time`. A band
    that wraps past midnight is split into two, because a string range query
    cannot express "22:40–00:40" in one clause and silently returning nothing
    for the wrap would drop every late-evening brief_time in that zone.
    """
    seen: set[int] = set()
    bands: list[tuple[str, str]] = []
    for zone_name in zones:
        offset = _offset_minutes(zone_name, tick)
        if offset in seen:
            continue
        seen.add(offset)
        tick_minute_of_day = tick.hour * 60 + tick.minute
        low = tick_minute_of_day + LEAD_MIN_MINUTES + offset
        high = tick_minute_of_day + LEAD_MAX_MINUTES + offset + tick_minutes
        bands.extend(_split_wrap(low, high))
    return bands


def _split_wrap(low: int, high: int) -> list[tuple[str, str]]:
    low %= 1440
    high %= 1440
    if low <= high:
        return [(_hhmm(low), _hhmm(high))]
    return [(_hhmm(low), "23:59"), ("00:00", _hhmm(high))]


def _hhmm(minute_of_day: int) -> str:
    minute_of_day %= 1440
    return f"{minute_of_day // 60:02d}:{minute_of_day % 60:02d}"


def _offset_minutes(zone_name: str, moment: dt.datetime) -> int:
    offset = moment.astimezone(ZoneInfo(zone_name)).utcoffset() or dt.timedelta()
    return int(offset.total_seconds() // 60)


class SubjectRepository:
    def __init__(self, db) -> None:  # noqa: ANN001
        self._db = db

    async def live_timezones(self) -> list[str]:
        """Distinct zones among schedulable users.

        `distinct` rather than a scan: the cardinality is zones, not users, and
        it is the input to the band narrowing rather than to the wave itself.
        """
        zones = await self._db.users.distinct(
            "timezone", {"status": {"$in": list(SCHEDULABLE_STATUSES)}}
        )
        return [z for z in zones if z]

    async def candidates(
        self, tick: dt.datetime, *, tick_minutes: int = TICK_MINUTES
    ) -> list[BriefSubject]:
        """Subjects worth evaluating at this tick (narrowed, not decided)."""
        zones = await self.live_timezones()
        if not zones:
            return []
        bands = offset_bands(zones, tick, tick_minutes=tick_minutes)
        clauses = [{"brief_time": {"$gte": low, "$lte": high}} for low, high in bands]

        pipeline: list[dict] = [
            {"$match": {"$or": clauses}},
            {
                "$lookup": {
                    "from": "users",
                    "localField": "user_id",
                    "foreignField": "_id",
                    "as": "user",
                }
            },
            {"$unwind": "$user"},
            {"$match": {"user.status": {"$in": list(SCHEDULABLE_STATUSES)}}},
            {
                "$lookup": {
                    "from": "subscriptions",
                    "let": {"uid": "$user_id"},
                    "pipeline": [
                        {"$match": {"$expr": {"$eq": ["$user_id", "$$uid"]}}},
                        # One row is enough: §6.4's partial unique index allows
                        # at most one ACTIVE subscription per user, and a
                        # cancelled history row cannot out-rank it here.
                        {"$sort": {"created_at": -1}},
                        {"$limit": 1},
                    ],
                    "as": "subscription",
                }
            },
        ]

        subjects: list[BriefSubject] = []
        async for doc in self._db.profiles.aggregate(pipeline):
            subject = self._to_subject(doc, tick)
            if subject is not None:
                subjects.append(subject)
        return subjects

    def _to_subject(self, doc: dict, tick: dt.datetime) -> BriefSubject | None:
        user = doc.get("user") or {}
        timezone = user.get("timezone")
        locale = user.get("locale")
        if not timezone or not locale:
            # §2.4 forbids guessing a language and §5.3 forbids guessing a
            # place. A profile missing either is a data defect to be reported,
            # not a brief to be improvised.
            logger.warning(
                "profile skipped: no timezone or locale",
                extra={"user_id": str(doc.get("user_id"))},
            )
            return None

        subscription = (doc.get("subscription") or [{}])[0]
        entitlement = Entitlement(
            plan=subscription.get("plan"),
            status=subscription.get("status"),
            trial_ends_at=subscription.get("trial_ends_at"),
        )
        # §7.1's panchang facts are computed FOR a place, and this is where the
        # tick learns which. Omitting it does not fail — `CompositeBriefFacts`
        # simply skips the panchang half — so a scheduled brief silently became
        # chart-only while the regenerate path, which loads the subject through
        # `wiring.load_subject`, kept its timings. Two loaders, one shape: they
        # must agree, and `test_repository_mongo.py` now asserts they do.
        place = doc.get("brief_place") or {}
        return BriefSubject(
            user_id=str(doc["user_id"]),
            locale=locale,
            timezone=timezone,
            brief_time=doc.get("brief_time") or DEFAULT_BRIEF_TIME,
            density=density_from(doc.get("density")),
            tier=tier_for(entitlement, now=tick),
            follow_timezone=doc.get("follow_timezone", True),
            lat=place.get("lat"),
            lon=place.get("lon"),
        )


def density_from(value: str | None) -> Density:
    """§28.2: the default is "interest level from onboarding", and MED where
    that was never captured — never HIGH, which would show a skeptic the
    choghadiya strip on their first morning."""
    try:
        return Density(value) if value else Density.MED
    except ValueError:
        logger.warning("unknown density on profile — using MED", extra={"density": value})
        return Density.MED


def subjects_by_tier(subjects: Sequence[BriefSubject]) -> dict[Tier, int]:
    """Counts per §7.1 queue. Logged by the tick so a wave that generated
    nothing can be told apart from a wave that found nobody."""
    counts: dict[Tier, int] = {tier: 0 for tier in Tier}
    for subject in subjects:
        counts[subject.tier] += 1
    return counts
