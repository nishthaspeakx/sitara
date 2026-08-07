"""Sunrise-anchored day divisions: rahu kaal, yamaganda, gulikai, abhijit and
the sixteen choghadiya parts (SPEC §5.2).

SCOPE (decision D1, §32.2): this is CALENDAR INTERPRETATION, not astronomy.
DivineAPI is primary for the served value; this module exists so that

  * §8's degradation ladder has a real internal rung when DivineAPI is down, and
  * the Layer-D comparison job has an independent third opinion.

The arithmetic is deterministic and fully tested. The RULE TABLES below are
tradition, not physics — they are Jyotish-adjudicable and carried in golden-set
for case-by-case sign-off (§5.2 Layer C).

Everything is measured from the LOCAL weekday and the LOCAL solar day. Reading
a weekday off a UTC instant would put rahu kaal on the wrong day for a large
part of the world (§5.3).
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sitara_schemas.facts import Choghadiya, DayTimingKind, TimingQuality

from sitara_astro.engine.inputs import Place
from sitara_astro.engine.riseset import SolarDay, sun_day

DAY_PARTS = 8
MUHURTAS_PER_DAY = 15  # abhijit is the 8th of fifteen

# The seven-name cycle. Both day and night sequences walk this ring; only the
# weekday's entry point differs.
CHOGHADIYA_CYCLE: tuple[Choghadiya, ...] = (
    Choghadiya.UDVEG,
    Choghadiya.CHAR,
    Choghadiya.LABH,
    Choghadiya.AMRIT,
    Choghadiya.KAAL,
    Choghadiya.SHUBH,
    Choghadiya.ROG,
)

CHOGHADIYA_QUALITY: dict[Choghadiya, TimingQuality] = {
    Choghadiya.AMRIT: TimingQuality.AUSPICIOUS,
    Choghadiya.SHUBH: TimingQuality.AUSPICIOUS,
    Choghadiya.LABH: TimingQuality.AUSPICIOUS,
    Choghadiya.CHAR: TimingQuality.NEUTRAL,
    Choghadiya.UDVEG: TimingQuality.INAUSPICIOUS,
    Choghadiya.KAAL: TimingQuality.INAUSPICIOUS,
    Choghadiya.ROG: TimingQuality.INAUSPICIOUS,
}

# Weekday (0=Sunday … 6=Saturday) → which of the eight day parts the band
# occupies, 1-indexed. Published Drik Panchang tables.
_RAHU_KAAL_PART = (8, 2, 7, 5, 6, 4, 3)
_YAMAGANDA_PART = (5, 4, 3, 2, 1, 7, 6)
_GULIKAI_PART = (7, 6, 5, 4, 3, 2, 1)


@dataclass(frozen=True)
class DayTiming:
    """One window. Mirrors DayTimingValue but stays engine-side: the fact
    builder attaches IDs, precision and provenance."""

    timing: DayTimingKind
    starts_utc: datetime
    ends_utc: datetime
    quality: TimingQuality
    choghadiya: Choghadiya | None = None
    part_index: int | None = None


def sunday_index(local_date: date) -> int:
    """0=Sunday … 6=Saturday — the ordering every panchang table is written in."""
    return (local_date.weekday() + 1) % 7


def _boundaries(start: datetime, span: timedelta, count: int) -> list[datetime]:
    """`count`+1 instants partitioning [start, start+span] with EXACT shared
    endpoints — dividing once and multiplying repeatedly leaves microsecond
    gaps between adjacent windows, and a user must never see a hole between
    two consecutive timings."""
    return [start + span * i / count for i in range(count + 1)]


def _band(
    day: SolarDay, kind: DayTimingKind, part_number: int, quality: TimingQuality
) -> DayTiming:
    edges = _boundaries(day.sunrise, day.day_length, DAY_PARTS)
    return DayTiming(
        timing=kind,
        starts_utc=edges[part_number - 1],
        ends_utc=edges[part_number],
        quality=quality,
    )


def _abhijit(day: SolarDay) -> DayTiming:
    """The 8th of fifteen equal muhurtas — the one auspicious band of the day."""
    muhurta = day.day_length / MUHURTAS_PER_DAY
    start = day.sunrise + muhurta * 7
    return DayTiming(
        timing=DayTimingKind.ABHIJIT,
        starts_utc=start,
        ends_utc=start + muhurta,
        quality=TimingQuality.AUSPICIOUS,
    )


def _choghadiya_run(
    start: datetime, span: timedelta, first_index: int, kind: DayTimingKind
) -> list[DayTiming]:
    edges = _boundaries(start, span, DAY_PARTS)
    run: list[DayTiming] = []
    for i in range(DAY_PARTS):
        name = CHOGHADIYA_CYCLE[(first_index + i) % len(CHOGHADIYA_CYCLE)]
        run.append(
            DayTiming(
                timing=kind,
                starts_utc=edges[i],
                ends_utc=edges[i + 1],
                quality=CHOGHADIYA_QUALITY[name],
                choghadiya=name,
                part_index=i + 1,
            )
        )
    return run


def day_timings(local_date: date, place: Place) -> list[DayTiming]:
    """Every sunrise-anchored window for one local date at one place.

    Raises NoRiseOrSet (an AstroError) where the Sun does not rise or set —
    there is no honest day division without a sunrise (§5.3).
    """
    day = sun_day(local_date, place)
    weekday = sunday_index(local_date)

    timings = [
        _band(day, DayTimingKind.RAHU_KAAL, _RAHU_KAAL_PART[weekday], TimingQuality.INAUSPICIOUS),
        _band(day, DayTimingKind.YAMAGANDA, _YAMAGANDA_PART[weekday], TimingQuality.INAUSPICIOUS),
        _band(day, DayTimingKind.GULIKAI, _GULIKAI_PART[weekday], TimingQuality.INAUSPICIOUS),
        _abhijit(day),
    ]
    # Day sequence enters the ring at weekday*3; night five steps further on.
    timings += _choghadiya_run(
        day.sunrise, day.day_length, (weekday * 3) % 7, DayTimingKind.CHOGHADIYA_DAY
    )
    timings += _choghadiya_run(
        day.sunset, day.night_length, (weekday * 3 + 5) % 7, DayTimingKind.CHOGHADIYA_NIGHT
    )
    return timings
