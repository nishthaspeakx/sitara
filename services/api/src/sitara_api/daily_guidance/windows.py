"""§7.1's lead window, as arithmetic.

    "Celery Beat ticks every 15 min, enqueuing a generation wave for users
    whose local brief_time falls 90–30 min ahead (staggered lead). … Load
    smoothing: waves spread across the 60-min lead window hashed by user_id;
    IST 07:00 is the global spike (≈60% of India users in one band)."

Two sentences, one mechanism, and it is worth being explicit about how they fit
together — because the obvious reading of the first sentence alone is wrong.

A 60-minute-wide window sampled every 15 minutes contains each user for FOUR
consecutive ticks. Selecting on window membership alone would therefore enqueue
every user four times and lean on §32.13's idempotency key to throw three of
them away — which works, and wastes three quarters of the wave's queue traffic
at exactly the moment §7.1 is trying to smooth. The hash is what makes the
window a schedule rather than a filter: each user gets a stable lead offset in
[30, 90) minutes, and fires at the ONE tick that offset lands in. Membership is
then a consequence, not a test, and the IST-07:00 band arrives spread evenly
across the hour instead of all at once.

Everything here is pure and clock-driven: no database, no Celery, no network.
That is deliberate — this is the part that has to be right on a DST boundary at
the date line, and none of those cases need infrastructure to reproduce.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from collections.abc import Iterable, Iterator
from zoneinfo import ZoneInfo

from sitara_api.daily_guidance.types import (
    GENERATED_TIERS,
    BriefSubject,
    WaveMember,
    WaveReport,
)

#: §7.1's window, in minutes ahead of the brief. The lead is drawn from
#: [LEAD_MIN, LEAD_MAX) so a user always has at least 30 minutes of generation
#: headroom and never sits in the queue longer than 90.
LEAD_MIN_MINUTES = 30
LEAD_MAX_MINUTES = 90
LEAD_SPREAD_MINUTES = LEAD_MAX_MINUTES - LEAD_MIN_MINUTES

#: "Celery Beat ticks every 15 min".
TICK_MINUTES = 15

#: §7.1's default, and §23.5's brief-time picker default: 07:00 local.
DEFAULT_BRIEF_TIME = "07:00"


class InvalidBriefTime(ValueError):
    """`brief_time` is stored as zero-padded local "HH:MM" and nothing else.

    Loud rather than defaulted: silently substituting 07:00 for a corrupt value
    would deliver a brief at a time the user did not choose, and they would have
    no way to tell that from a bug in the scheduler.
    """


def parse_brief_time(value: str) -> tuple[int, int]:
    """"HH:MM" → (hour, minute). Zero-padded, 24-hour, local."""
    try:
        hour_text, minute_text = value.split(":")
        hour, minute = int(hour_text), int(minute_text)
    except (ValueError, AttributeError):
        raise InvalidBriefTime(f"brief_time must be 'HH:MM', got {value!r}") from None
    if len(hour_text) != 2 or len(minute_text) != 2:
        raise InvalidBriefTime(f"brief_time must be zero-padded 'HH:MM', got {value!r}")
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise InvalidBriefTime(f"brief_time out of range: {value!r}")
    return hour, minute


def lead_minutes(user_id: str) -> int:
    """This user's stable position in the 60-minute lead window (§7.1).

    blake2b rather than `hash()`: the built-in is salted per process, so the
    same user would draw a different slot on every worker and the smoothing
    would degrade to noise — the one property this function exists to provide.
    """
    digest = hashlib.blake2b(user_id.encode("utf-8"), digest_size=8).digest()
    return LEAD_MIN_MINUTES + int.from_bytes(digest, "big") % LEAD_SPREAD_MINUTES


def local_instant(local_date: dt.date, hour: int, minute: int, zone: ZoneInfo) -> dt.datetime:
    """The instant a wall-clock time occurs on a local date — DST included.

    **Returned in UTC, always.** Not a stylistic choice: PEP 495 makes an
    aware datetime that is AMBIGUOUS in its zone (a fall-back repeat) compare
    unequal to its own instant in any other zone, while still comparing neither
    less nor greater than it. On 2026-11-01 in New York, 01:30 fold=0 is
    05:30 UTC by `astimezone`, yet `== ` against 05:30 UTC is False and so are
    `<` and `>`. Trichotomy does not hold, so any downstream `==`, `in`, dict
    key or sort involving such a value is quietly wrong twice a year. Handing
    back UTC removes the entire class: the local date is returned separately by
    every caller that needs one, and local rendering is explicit where it
    happens (`templates._clock`, the notification's expiry).

    Two transition-day cases §23.9 requires us to get right:

    * **Ambiguous** (clocks go back; 07:00 happens twice). `fold=0` takes the
      FIRST occurrence, so the brief is early-in-the-repeat rather than late.
    * **Nonexistent** (clocks go forward; 07:00 never happens). The naive value
      does not round-trip through UTC, and we advance to the first instant that
      does exist. §23.9's rule is that the brief lands at the local target time
      "in all" zones — on a spring-forward day the nearest truth to the target
      is the moment the clock reaches it.
    """
    naive = dt.datetime(local_date.year, local_date.month, local_date.day, hour, minute)
    candidate = naive.replace(tzinfo=zone, fold=0)
    if candidate.astimezone(dt.UTC).astimezone(zone).replace(tzinfo=None) == naive:
        return candidate.astimezone(dt.UTC)
    # A gap. Step forward a minute at a time to the first existing wall clock;
    # no transition in tzdb is longer than two hours, and this runs at most
    # once per user per year.
    for offset in range(1, 121):
        shifted = naive + dt.timedelta(minutes=offset)
        probe = shifted.replace(tzinfo=zone, fold=0)
        if probe.astimezone(dt.UTC).astimezone(zone).replace(tzinfo=None) == shifted:
            return probe.astimezone(dt.UTC)
    return candidate.astimezone(dt.UTC)


def candidate_due_instants(
    subject: BriefSubject, tick: dt.datetime
) -> Iterator[tuple[str, dt.datetime]]:
    """The user's brief instants for the local dates near this tick.

    Three local dates are considered — yesterday, today and tomorrow in the
    user's own zone — because "which local date is the next brief for?" has no
    single answer near midnight or across the date line. §32.13 requires that
    crossings "can neither double-fire nor skip"; generating candidates for all
    three and letting the window decide is what makes both halves true, and the
    idempotency key catches anything the window lets through twice.
    """
    zone = ZoneInfo(subject.timezone)
    hour, minute = parse_brief_time(subject.brief_time)
    local_today = tick.astimezone(zone).date()
    for delta in (-1, 0, 1):
        local_date = local_today + dt.timedelta(days=delta)
        yield local_date.isoformat(), local_instant(local_date, hour, minute, zone)


#: How far the cheap pre-check widens its wall-clock window before the exact
#: test runs. It has to cover the largest offset change a zone can make between
#: the tick and the brief — an hour of DST, doubled for headroom. Too small and
#: a transition-day brief is dropped by an optimisation; too large only costs
#: a few exact checks that then decline.
_PRECHECK_SLACK_MINUTES = 120


def wave_member(
    subject: BriefSubject, tick: dt.datetime, *, tick_minutes: int = TICK_MINUTES
) -> WaveMember | None:
    """Is this subject due to be GENERATED at this tick?

    Exactly one tick per user per local date returns a member: the tick whose
    interval contains `due_at - lead`, where `lead` is the user's stable draw
    from the 60-minute window. Returning None is the overwhelmingly common
    answer — 95 of every 96 daily ticks, for a given user — and that asymmetry
    is what the structure below is for.

    A cheap wall-clock pre-check runs first: at `tick + lead` the user's local
    clock reads some minute of the day, and their brief_time has to be within a
    tick of it or there is nothing to compute. Only survivors reach
    `local_instant`, which is the expensive part (it round-trips through UTC to
    detect DST gaps). The pre-check is deliberately a SUPERSET — widened by
    `_PRECHECK_SLACK_MINUTES` so a zone whose offset moves between the tick and
    the brief cannot be filtered out by an optimisation — and the exact test
    below is still what decides.
    """
    lead = dt.timedelta(minutes=lead_minutes(subject.user_id))
    interval = dt.timedelta(minutes=tick_minutes)
    zone = ZoneInfo(subject.timezone)
    hour, minute = parse_brief_time(subject.brief_time)
    brief_minute_of_day = hour * 60 + minute

    local_target = (tick + lead).astimezone(zone)
    target_minute_of_day = local_target.hour * 60 + local_target.minute
    delta = (brief_minute_of_day - target_minute_of_day) % 1440
    if not (
        delta <= tick_minutes + _PRECHECK_SLACK_MINUTES
        or delta >= 1440 - _PRECHECK_SLACK_MINUTES
    ):
        return None

    # The exact test. Yesterday/today/tomorrow in the user's own zone, because
    # near midnight and across the date line there is no single answer to
    # "which local date is the next brief for?" (§32.13).
    for local_date, due_at in candidate_due_instants(subject, tick):
        start_at = due_at - lead
        if tick <= start_at < tick + interval:
            return WaveMember(
                subject=subject,
                local_date=local_date,
                due_at=due_at,
                start_at=start_at,
                slot_minutes=int(lead.total_seconds() // 60),
            )
    return None


def select_wave(
    subjects: Iterable[BriefSubject],
    tick: dt.datetime,
    *,
    tick_minutes: int = TICK_MINUTES,
    already_generated: frozenset[tuple[str, str]] = frozenset(),
) -> tuple[list[WaveMember], WaveReport]:
    """One tick's generation wave (§7.1), plus what it decided and why.

    `already_generated` is the set of (user_id, local_date) pairs §32.13 has
    already bound. It is a cheap pre-filter, not the guarantee — the guarantee
    is the unique index behind the idempotent write, because two workers can
    read this set at the same moment and both find it empty.
    """
    members: list[WaveMember] = []
    dormant = 0
    already = 0
    by_slot: dict[int, int] = {}

    for subject in subjects:
        # §7.1: "dormant users get on-open generation only — no waste". The
        # check is here rather than in the query so the tick can report what it
        # declined to do; a wave that silently generates nothing looks
        # identical to a broken scheduler.
        if subject.tier not in GENERATED_TIERS:
            dormant += 1
            continue
        member = wave_member(subject, tick, tick_minutes=tick_minutes)
        if member is None:
            continue
        if (subject.user_id, member.local_date) in already_generated:
            already += 1
            continue
        members.append(member)
        by_slot[member.slot_minutes] = by_slot.get(member.slot_minutes, 0) + 1

    # §7.1's priority queues, applied to the enqueue order: within one tick a
    # paying user's brief is composed before a trial user's, so a queue-depth
    # breach (the §7.1 cost lever) degrades the least-committed briefs first.
    members.sort(key=lambda m: (GENERATED_TIERS.index(m.subject.tier), m.start_at))

    return members, WaveReport(
        tick=tick,
        selected=len(members),
        skipped_dormant=dormant,
        skipped_already_generated=already,
        by_slot=by_slot,
    )


def ticks_for_day(start: dt.datetime, *, tick_minutes: int = TICK_MINUTES) -> list[dt.datetime]:
    """Every Beat tick in the 24 hours from `start`. Used by the load
    simulation and by the timezone-matrix suite (§23.9)."""
    count = (24 * 60) // tick_minutes
    return [start + dt.timedelta(minutes=tick_minutes * i) for i in range(count)]
