"""§7.3's minute pool and §32.9's warnings.

Pure arithmetic over a quota and a monotonic clock, which is why it is tested
with neither a socket nor a database: the two failures worth preventing — a
user charged for minutes they did not speak, and a call cut without the notices
§32.9 promises — are both reproducible in milliseconds.
"""

from __future__ import annotations

import datetime as dt

import pytest

from sitara_api.voice.entitlements import (
    MINUTE_POOL,
    CallPlan,
    Entitlement,
    MinuteMeter,
    _plan_from,
    period_start_for,
)


def _meter(quota: int | None, used: float = 0.0) -> MinuteMeter:
    return MinuteMeter(
        entitlement=Entitlement(
            plan=CallPlan.MONTHLY if quota else CallPlan.PREMIUM,
            quota_minutes=quota,
            used_minutes=used,
        )
    )


# ---------------------------------------------------------------------------
# the pool
# ---------------------------------------------------------------------------


def test_the_pool_is_section_29s_row() -> None:
    """"trial 60 · monthly 300 · annual/premium 900/unlimited-fair-use".

    §7.3's own sentence says "300 min/mo Basic, 900 Premium", using "Premium"
    for the 900 §29 gives to *annual*. The numbers agree and one label does not;
    §29's channel table is the specific statement and this follows it. Asserted
    rather than left to a reader who checks this against §7.3 and finds a
    mismatch nobody appears to have noticed.
    """
    assert MINUTE_POOL[CallPlan.TRIAL] == 60
    assert MINUTE_POOL[CallPlan.MONTHLY] == 300
    assert MINUTE_POOL[CallPlan.ANNUAL] == 900
    assert MINUTE_POOL[CallPlan.PREMIUM] is None


def test_the_unlimited_tier_has_no_invented_ceiling() -> None:
    """§7.3 says a soft limit ends in "a gentle in-locale notice + text-mode"
    and names NO NUMBER for it. So there is none here — a plausible constant
    would be inventing the one number a user is eventually told they exceeded.
    """
    meter = _meter(None)
    meter.start(0.0)
    assert meter.tick(60 * 60 * 24) == (), "an unlimited pool warned about something"
    assert not meter.exhausted(60 * 60 * 24)


def test_an_unrecognised_plan_grants_nothing() -> None:
    """§30.3 already contemplates plans this code has never seen — founding
    offers, gifts, store-billing wrappers. On the day one ships, the failure
    worth having is "calls are unavailable" rather than a silent grant of
    somebody else's quota."""
    assert _plan_from({"plan": "founding_year_one"}) is CallPlan.NONE
    assert _plan_from(None) is CallPlan.NONE
    assert MINUTE_POOL[CallPlan.NONE] == 0


# ---------------------------------------------------------------------------
# §32.9's warnings
# ---------------------------------------------------------------------------


def test_both_warnings_fire_once_each() -> None:
    """§32.9: "warnings at 5 and 2 minutes (in-locale, in Tara's voice, once
    each)". The once-ness lives in the meter and not in a client that could be
    reloaded — a reconnect inside §32.11's window must not re-announce a warning
    the user already heard."""
    meter = _meter(300, used=294.0)  # 6 minutes left
    meter.start(0.0)

    assert meter.tick(0.0) == ()
    assert meter.tick(70.0) == (5,)
    assert meter.tick(80.0) == ()
    assert meter.tick(250.0) == (2,)
    assert meter.tick(260.0) == ()


def test_a_long_synthesis_does_not_skip_the_two_minute_warning() -> None:
    """The bug this shape prevents: crossing 6.0 → 1.5 minutes in ONE tick.

    A naive implementation checks the highest unfired threshold, announces "5
    minutes left" to somebody who has 1.5, and never announces 2 at all. Both
    thresholds are evaluated against the new remaining value on every tick, so
    the caller gets both and can announce the last one.
    """
    meter = _meter(300, used=294.0)
    meter.start(0.0)
    assert meter.tick(270.0) == (5, 2), "the tail warning was skipped"


def test_metering_stops_when_the_session_is_text_mode() -> None:
    """§32.9: "metering stops the moment the session is text-mode".
    §32.11: "metering resumed only on resume".

    A meter running off wall-clock from `session.start` would charge a user for
    the four minutes they spent reading a handoff notice.
    """
    meter = _meter(300)
    meter.start(0.0)
    meter.stop(60.0)
    assert meter.spent_seconds(600.0) == pytest.approx(60.0)

    meter.start(600.0)
    assert meter.spent_seconds(660.0) == pytest.approx(120.0)


def test_stopping_twice_does_not_refund_minutes() -> None:
    """`session.end`, a handoff and a reap can all land on one call."""
    meter = _meter(300)
    meter.start(0.0)
    meter.stop(60.0)
    meter.stop(120.0)
    assert meter.spent_seconds(200.0) == pytest.approx(60.0)


# ---------------------------------------------------------------------------
# the chip, and the period
# ---------------------------------------------------------------------------


def test_the_chip_floors_the_minutes_it_promises() -> None:
    """§25.3's "⏳ 240 min left". Telling somebody they have 4 minutes when
    they have 3.6 is a promise the meter will break 36 seconds later."""
    chip = Entitlement(
        plan=CallPlan.MONTHLY, quota_minutes=300, used_minutes=296.4
    ).as_chip()
    assert chip["minutes_left"] == 3
    assert chip["unlimited"] is False

    unlimited = Entitlement(
        plan=CallPlan.PREMIUM, quota_minutes=None, used_minutes=999.0
    ).as_chip()
    assert unlimited["unlimited"] is True
    assert unlimited["minutes_left"] is None


def test_an_overrun_pool_reads_as_empty_and_never_as_negative() -> None:
    entitlement = Entitlement(
        plan=CallPlan.MONTHLY, quota_minutes=300, used_minutes=305.0
    )
    assert entitlement.remaining_minutes == 0.0
    assert entitlement.exhausted


def test_the_period_is_anchored_on_the_subscription_day_not_the_first() -> None:
    """A subscription taken on the 20th that reset on the 1st would hand its
    first month eleven free days, and every month after that would end on a
    different day from the one the user is billed on."""
    now = dt.datetime(2026, 8, 14, tzinfo=dt.UTC)
    start = period_start_for(
        CallPlan.MONTHLY,
        subscribed_at=dt.datetime(2026, 1, 20, 9, 30, tzinfo=dt.UTC),
        now=now,
    )
    assert start == dt.datetime(2026, 7, 20, 9, 30, tzinfo=dt.UTC)


def test_a_month_end_subscription_never_skips_a_period() -> None:
    """The 31st does not exist in February. Clamping to the 28th moves the
    boundary by three days; not clamping loses the month entirely."""
    now = dt.datetime(2026, 3, 1, tzinfo=dt.UTC)
    start = period_start_for(
        CallPlan.MONTHLY,
        subscribed_at=dt.datetime(2026, 1, 31, 9, 30, tzinfo=dt.UTC),
        now=now,
    )
    assert start is not None and start.month == 2


def test_a_trial_pool_is_the_whole_trial_and_never_rolls_over() -> None:
    """§10-20 makes the trial seven days. Sixty minutes over seven days is a
    trial TOTAL, and a monthly reading would silently double the pool for
    anyone whose trial straddled a month boundary."""
    subscribed = dt.datetime(2026, 7, 30, tzinfo=dt.UTC)
    start = period_start_for(
        CallPlan.TRIAL, subscribed_at=subscribed, now=dt.datetime(2026, 8, 3, tzinfo=dt.UTC)
    )
    assert start == subscribed
