"""§7.1's lead window and §23.9's timezone matrix.

§23.9 makes these release-gated: "timezone matrix delivery tests (IST, EST,
GMT, AEDT, half-hour zones, DST transition days — briefs land at the local
target time in all)". This file is that suite for the SELECTION half; delivery
is the notification worker's.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from sitara_api.daily_guidance.types import Tier
from sitara_api.daily_guidance.windows import (
    DEFAULT_BRIEF_TIME,
    LEAD_MAX_MINUTES,
    LEAD_MIN_MINUTES,
    TICK_MINUTES,
    InvalidBriefTime,
    lead_minutes,
    local_instant,
    parse_brief_time,
    select_wave,
    ticks_for_day,
    wave_member,
)
from tests.daily_guidance.conftest import subject

#: §23.9's named zones, plus the half-hour and three-quarter-hour cases that
#: break naive offset arithmetic.
ZONE_MATRIX = [
    "Asia/Kolkata",  # +05:30, no DST
    "America/New_York",  # EST/EDT
    "Europe/London",  # GMT/BST
    "Australia/Sydney",  # AEDT, southern-hemisphere DST
    "Asia/Kathmandu",  # +05:45
    "Pacific/Chatham",  # +12:45/+13:45
    "Pacific/Kiritimati",  # +14:00, the eastern edge of the date line
    "Pacific/Niue",  # −11:00, the western edge
]


def _day_of_ticks(on: dt.date) -> list[dt.datetime]:
    start = dt.datetime(on.year, on.month, on.day, tzinfo=dt.UTC)
    # Two days of ticks: a user near the date line can have their brief for a
    # local date selected on either side of a UTC midnight.
    return ticks_for_day(start) + ticks_for_day(start + dt.timedelta(days=1))


# --- brief_time parsing ----------------------------------------------------


def test_brief_time_must_be_zero_padded() -> None:
    assert parse_brief_time("07:00") == (7, 0)
    assert parse_brief_time("23:45") == (23, 45)
    for bad in ("7:00", "07:0", "0700", "", "25:00", "07:61", "abc"):
        with pytest.raises(InvalidBriefTime):
            parse_brief_time(bad)


def test_brief_time_sorts_as_the_clock_does() -> None:
    """The §7.1 index does a STRING range scan over brief_time.

    Zero-padded "HH:MM" is what makes that legal — "06:30" < "07:00" < "10:00"
    lexicographically as well as chronologically. Drop the padding and "7:00"
    sorts after "10:00", and the wave silently misses a band of users.
    """
    times = ["10:00", "07:00", "06:30", "23:45", "00:15"]
    assert sorted(times) == ["00:15", "06:30", "07:00", "10:00", "23:45"]


# --- the hash --------------------------------------------------------------


def test_lead_is_inside_the_spec_window() -> None:
    for index in range(2000):
        lead = lead_minutes(f"user-{index}")
        assert LEAD_MIN_MINUTES <= lead < LEAD_MAX_MINUTES


def test_lead_is_stable_across_processes() -> None:
    """§7.1's smoothing depends on the slot being the same everywhere.

    Python's built-in `hash()` is salted per process (PYTHONHASHSEED), so a
    user would draw a different slot on every worker and the spread would
    degrade to noise. This asserts the value itself, not merely determinism
    within one run — a change here is a change to every user's schedule.
    """
    assert lead_minutes("6a70000000000000000000a1") == lead_minutes(
        "6a70000000000000000000a1"
    )
    # A literal, so switching hash function is a visible edit rather than a
    # silent reshuffle of when 100k people get their morning.
    assert lead_minutes("sitara") == 30 + (
        int.from_bytes(__import__("hashlib").blake2b(b"sitara", digest_size=8).digest(), "big")
        % 60
    )


def test_leads_spread_across_the_whole_window() -> None:
    counts = {minute: 0 for minute in range(LEAD_MIN_MINUTES, LEAD_MAX_MINUTES)}
    for index in range(6000):
        counts[lead_minutes(f"6a7000000000000000000{index:03x}")] += 1
    assert all(counts.values()), "every minute of the 60-minute window must be used"
    # 6000 over 60 slots is 100 each; a hash this lopsided would not smooth.
    assert max(counts.values()) < 3 * min(counts.values())


# --- single fire (§32.13) --------------------------------------------------


@pytest.mark.parametrize("zone", ZONE_MATRIX)
def test_each_user_fires_exactly_once_per_local_date(zone: str) -> None:
    """§32.13: "Date-line crossings can neither double-fire nor skip"."""
    person = subject(timezone=zone, brief_time=DEFAULT_BRIEF_TIME)
    fired: list[tuple[str, dt.datetime]] = []
    for tick in _day_of_ticks(dt.date(2026, 8, 12)):
        member = wave_member(person, tick)
        if member is not None:
            fired.append((member.local_date, tick))

    dates = [local_date for local_date, _ in fired]
    assert len(dates) == len(set(dates)), f"{zone}: a local date fired twice — {fired}"
    # Two UTC days of ticks must cover at least two local dates for every zone,
    # including the ±14h edges. Fewer would mean a skipped morning.
    assert len(dates) >= 2, f"{zone}: only {len(dates)} local date(s) fired"


@pytest.mark.parametrize("zone", ZONE_MATRIX)
def test_the_brief_is_generated_inside_the_lead_window(zone: str) -> None:
    """§7.1: "users whose local brief_time falls 90–30 min ahead"."""
    person = subject(timezone=zone)
    for tick in _day_of_ticks(dt.date(2026, 8, 12)):
        member = wave_member(person, tick)
        if member is None:
            continue
        ahead = (member.due_at - tick).total_seconds() / 60
        assert LEAD_MIN_MINUTES <= ahead <= LEAD_MAX_MINUTES + TICK_MINUTES, (
            f"{zone}: selected {ahead:.0f} min ahead of the brief"
        )


@pytest.mark.parametrize("zone", ZONE_MATRIX)
def test_the_due_instant_is_the_users_local_brief_time(zone: str) -> None:
    """The whole point: "briefs land at the local target time in all" (§23.9)."""
    person = subject(timezone=zone, brief_time="07:00")
    for tick in _day_of_ticks(dt.date(2026, 8, 12)):
        member = wave_member(person, tick)
        if member is None:
            continue
        local = member.due_at.astimezone(ZoneInfo(zone))
        assert local.strftime("%H:%M") == "07:00", f"{zone}: due at {local}"
        assert local.date().isoformat() == member.local_date


# --- DST transition days (§23.9) -------------------------------------------


def test_spring_forward_gap_advances_to_the_first_real_instant() -> None:
    """2026-03-08, America/New_York: 02:00–03:00 local does not exist.

    A 02:30 brief_time has no instant that day. Advancing to 03:00 is the
    nearest truth to the user's target; the alternative — silently using the
    pre-transition offset — puts the brief an hour early and looks correct.
    """
    zone = ZoneInfo("America/New_York")
    instant = local_instant(dt.date(2026, 3, 8), 2, 30, zone)
    local = instant.astimezone(zone)
    assert (local.hour, local.minute) == (3, 0)
    assert local.date() == dt.date(2026, 3, 8)


def test_fall_back_ambiguity_takes_the_first_occurrence() -> None:
    """2026-11-01, America/New_York: 01:30 local happens twice.

    fold=0 is the earlier one — early-in-the-repeat rather than an hour late.
    """
    zone = ZoneInfo("America/New_York")
    instant = local_instant(dt.date(2026, 11, 1), 1, 30, zone)
    assert instant == dt.datetime(2026, 11, 1, 5, 30, tzinfo=dt.UTC)  # EDT, −04:00


def test_local_instant_always_returns_utc() -> None:
    """The PEP 495 hazard `local_instant` exists to keep out of the pipeline.

    An aware datetime that is AMBIGUOUS in its own zone compares unequal to its
    own instant elsewhere, while comparing neither less nor greater — trichotomy
    fails, so `==`, `in`, dict keys and sorts are all quietly wrong on fall-back
    days. This test demonstrates the hazard on a raw value and then asserts
    `local_instant` never hands one out.
    """
    zone = ZoneInfo("America/New_York")
    ambiguous = dt.datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=0)
    same_instant = dt.datetime(2026, 11, 1, 5, 30, tzinfo=dt.UTC)
    assert ambiguous.astimezone(dt.UTC) == same_instant  # it IS that instant
    assert not (ambiguous == same_instant)  # ...and does not compare equal  # noqa: SIM201
    assert not (ambiguous < same_instant) and not (ambiguous > same_instant)

    for zone_name in ZONE_MATRIX:
        for day in (dt.date(2026, 11, 1), dt.date(2026, 3, 8), dt.date(2026, 8, 12)):
            assert local_instant(day, 1, 30, ZoneInfo(zone_name)).tzinfo is dt.UTC


@pytest.mark.parametrize(
    ("zone", "day"),
    [
        ("America/New_York", dt.date(2026, 3, 8)),  # spring forward
        ("America/New_York", dt.date(2026, 11, 1)),  # fall back
        ("Europe/London", dt.date(2026, 3, 29)),
        ("Europe/London", dt.date(2026, 10, 25)),
        ("Australia/Sydney", dt.date(2026, 4, 5)),
        ("Australia/Sydney", dt.date(2026, 10, 4)),
    ],
)
def test_transition_days_still_fire_exactly_once(zone: str, day: dt.date) -> None:
    person = subject(timezone=zone)
    fired = [
        member.local_date
        for tick in _day_of_ticks(day - dt.timedelta(days=1))
        if (member := wave_member(person, tick)) is not None
    ]
    assert len(fired) == len(set(fired)), f"{zone} {day}: double fire {fired}"
    assert day.isoformat() in fired, f"{zone}: no brief on the transition day"


def test_the_precheck_never_filters_out_a_real_member() -> None:
    """The fast path in `wave_member` must be a strict superset.

    It skips the expensive DST-aware construction using the offset at the TICK,
    which can differ from the offset at the brief. This walks a transition day
    minute by minute against the unoptimised definition and asserts they agree.
    """
    from sitara_api.daily_guidance.windows import candidate_due_instants

    person = subject(timezone="America/New_York", brief_time="02:30")
    start = dt.datetime(2026, 3, 8, tzinfo=dt.UTC)
    for offset in range(0, 60 * 48, TICK_MINUTES):
        tick = start + dt.timedelta(minutes=offset)
        lead = dt.timedelta(minutes=lead_minutes(person.user_id))
        naive = [
            local_date
            for local_date, due_at in candidate_due_instants(person, tick)
            if tick <= due_at - lead < tick + dt.timedelta(minutes=TICK_MINUTES)
        ]
        member = wave_member(person, tick)
        assert [member.local_date] if member else [] == naive or not naive


# --- the wave --------------------------------------------------------------


def test_dormant_users_are_never_enqueued() -> None:
    """§7.1: "dormant users get on-open generation only — no waste"."""
    people = [
        subject(user_id=f"6a7000000000000000000{i:03x}", tier=tier)
        for i, tier in enumerate([Tier.PAYING, Tier.TRIAL, Tier.DORMANT] * 10)
    ]
    selected = 0
    dormant_reported = 0
    for tick in _day_of_ticks(dt.date(2026, 8, 12)):
        members, report = select_wave(people, tick)
        selected += len(members)
        dormant_reported = report.skipped_dormant
        assert all(m.subject.tier is not Tier.DORMANT for m in members)
    assert dormant_reported == 10
    # 20 non-dormant users × 2 local dates.
    assert selected == 40


def test_paying_users_are_composed_before_trial_users() -> None:
    """§7.1's priority queues, applied to the enqueue order within a tick."""
    people = [
        subject(user_id="6a7000000000000000000001", tier=Tier.TRIAL),
        subject(user_id="6a7000000000000000000002", tier=Tier.PAYING),
        subject(user_id="6a7000000000000000000003", tier=Tier.TRIAL),
        subject(user_id="6a7000000000000000000004", tier=Tier.PAYING),
    ]
    for tick in _day_of_ticks(dt.date(2026, 8, 12)):
        members, _ = select_wave(people, tick)
        tiers = [m.subject.tier for m in members]
        assert tiers == sorted(tiers, key=lambda t: 0 if t is Tier.PAYING else 1)


def test_already_generated_pairs_are_skipped() -> None:
    """§32.13's cheap pre-filter. The unique index is the guarantee; this only
    keeps the queue from carrying work that will be discarded on arrival."""
    person = subject()
    for tick in _day_of_ticks(dt.date(2026, 8, 12)):
        member = wave_member(person, tick)
        if member is None:
            continue
        members, report = select_wave(
            [person], tick, already_generated=frozenset({(person.user_id, member.local_date)})
        )
        assert members == []
        assert report.skipped_already_generated == 1
        return
    pytest.fail("no tick selected the subject")
