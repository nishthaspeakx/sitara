"""§32.1's inputs — the account facts §28.2's variants are chosen from.

This module reads; it does not decide. §32.1's precedence rule ("stack top-down
in fixed priority, max 2 banners + 1 pill") is evaluated in exactly one place,
`apps/web/src/lib/today-variant.ts`, because that is where the stack is
rendered. A server that also picked the variant would be a second
implementation of the same rule, and the two would disagree on the morning that
matters — the one with a festival, a travel banner and a grace notice at once.

So what crosses the wire is state, not verdicts: is there a festival today, is
travel active, which day of the trial is it. The rule reading them lives with
the layout it governs.
"""

from __future__ import annotations

import datetime as dt
import logging

from bson import ObjectId
from sitara_schemas.facts import FestivalObservanceValue
from sitara_schemas.today import PlanState, TodayFestival, TodayState, TodayTravel

from sitara_api.daily_guidance.priority import ENTITLED_STATUSES, TRIAL_PLANS
from sitara_api.daily_guidance.types import Brief, BriefSubject
from sitara_api.localisation import MissingString, resolve

logger = logging.getLogger(__name__)

#: §22.13's dunning statuses — "payment needs attention", full features intact.
GRACE_STATUSES: frozenset[str] = frozenset({"past_due", "in_grace"})

#: §28.2: "Trial: day-counter pill (subtle, never red) FROM DAY 4". Before day
#: four there is no pill at all, which is the §29.2 half of the rule: a counter
#: from day one is a countdown wearing a different hat.
TRIAL_PILL_FROM_DAY = 4


def plan_state(subscription: dict | None) -> PlanState:
    """§28.2's four commercial variants, from the subscription row.

    FREE is the residual and is deliberately last: a row that is missing,
    cancelled, expired or simply unrecognised all mean the same thing to this
    screen — no entitlement — and enumerating the ways that can happen would be
    a list that goes stale rather than a rule.
    """
    sub = subscription or {}
    status = sub.get("status")
    if status in GRACE_STATUSES:
        return PlanState.GRACE
    if status in ENTITLED_STATUSES:
        return PlanState.TRIAL if sub.get("plan") in TRIAL_PLANS else PlanState.PREMIUM
    return PlanState.FREE


def trial_day(subscription: dict | None, *, now: dt.datetime) -> int | None:
    """Which day of the trial this is, or None when no pill should show.

    Counts from the row's own start, not from "days remaining". §29.2 forbids
    countdowns, and "4 days left" is a countdown however gently it is phrased;
    "day 4" is a position, which is what §28.2 asked for.
    """
    sub = subscription or {}
    if sub.get("plan") not in TRIAL_PLANS or sub.get("status") not in ENTITLED_STATUSES:
        return None
    started = sub.get("created_at")
    if not isinstance(started, dt.datetime):
        return None
    if started.tzinfo is None:
        started = started.replace(tzinfo=dt.UTC)
    day = (now - started).days + 1
    return day if day >= TRIAL_PILL_FROM_DAY else None


def festival_from(brief: Brief, locale: str) -> TodayFestival | None:
    """The day's festival, named in the user's own language or not at all.

    §2.4: "a vendor's English festival name never reaches a user". A festival
    we cannot name is a banner we do not raise — the same answer the composer
    gives when it cannot write the card.
    """
    for snapshot in brief.snapshots:
        value = snapshot.value
        if not isinstance(value, FestivalObservanceValue):
            continue
        try:
            name = resolve(f"festivals.{value.festival_id}", locale)
        except MissingString:
            logger.warning(
                "festival unnamed in locale — no banner",
                extra={"festival_id": value.festival_id, "locale": locale},
            )
            return None
        return TodayFestival(
            name=name,
            tradition_label=_tradition_label(value, locale),
            date_label=brief.local_date,
        )
    return None


def _tradition_label(value: FestivalObservanceValue, locale: str) -> str:
    tradition = getattr(value, "tradition", None)
    if tradition is None:
        return ""
    slug = getattr(tradition, "value", str(tradition))
    try:
        return resolve(f"terms.tradition.{slug}", locale)
    except MissingString:
        return ""


async def build_state(
    db,  # noqa: ANN001
    subject: BriefSubject,
    brief: Brief,
    *,
    local_date: str,
    brief_count: int,
    stories_enabled: bool,
    now: dt.datetime | None = None,
) -> TodayState:
    """Assemble §28.2's variant inputs for this user, this morning.

    `brief_count` is passed in rather than counted here because the caller has
    already touched `daily_briefings` and a second round trip for a number it
    holds would be a query per page view on the app's busiest screen.
    """
    moment = now or dt.datetime.now(dt.UTC)
    oid = ObjectId(subject.user_id)

    profile = await db.profiles.find_one({"user_id": oid}) or {}
    subscription = await db.subscriptions.find_one(
        {"user_id": oid}, sort=[("created_at", -1)]
    )

    travel_doc = profile.get("travel") or {}
    travel = TodayTravel(
        active=bool(travel_doc.get("active")),
        city=travel_doc.get("city"),
    )

    return TodayState(
        # No brief has ever been generated. §28.2's first-session variant, and
        # §28.2's States row makes it the empty state too.
        first_session=brief_count == 0,
        # Exactly one, and it is this morning's. The celebration accent belongs
        # to the first brief a user ever receives, not to every morning until
        # they open a second one.
        first_morning=brief_count == 1 and brief.local_date == local_date,
        brief_time=subject.brief_time,
        travel=travel,
        festival=festival_from(brief, subject.locale),
        birthday=await _is_birthday(db, oid, local_date),
        birth_time_missing=await _birth_time_missing(db, oid),
        trial_day=trial_day(subscription, now=moment),
        plan=plan_state(subscription),
        # §30.6: the ring is hidden in P0. The component defaults `enabled` to
        # false for the same reason; this is the flag that would turn it on.
        story_ring_enabled=stories_enabled,
    )


async def _is_birthday(db, oid: ObjectId, local_date: str) -> bool:  # noqa: ANN001
    """Month and day match, in the user's LOCAL date (§32.13).

    Reads through `birth_details`, which is CSFLE-encrypted on the full payload
    (§6.4). Where the codec is not provisioned the date comes back as
    ciphertext and this answers False — a wrong birthday card is worse than a
    missing one, and this is not the surface to discover a crypto misconfig on.
    """
    doc = await db.birth_details.find_one({"user_id": oid})
    raw = (doc or {}).get("date")
    if not isinstance(raw, str):
        return False
    try:
        born = dt.date.fromisoformat(raw)
        today = dt.date.fromisoformat(local_date)
    except ValueError:
        return False
    return (born.month, born.day) == (today.month, today.day)


async def _birth_time_missing(db, oid: ObjectId) -> bool:  # noqa: ANN001
    """§28.2's missing-birth-time variant.

    "unknown" is the accuracy §5.3 treats as no time at all — a Moon-chart
    reading rather than a lagna-sensitive one — so it is what raises the chip.
    """
    doc = await db.birth_details.find_one({"user_id": oid})
    if doc is None:
        return True
    accuracy = doc.get("time_accuracy")
    return not isinstance(accuracy, str) or accuracy == "unknown"
