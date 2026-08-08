"""Panchang FactSnapshot emission (SPEC §34.2, §5.2 Layer A).

These facts are GLOBAL: the subject is `{geohash4}-{tradition}`, never a user
id. Thousands of users in one city share one panchang document (§7.1), and a
cache key must never be a location trace (§13).

Authority (decision D1, §32.2): the boundary and rise/set facts here are
deterministic astronomy and Layer A is authoritative for them. The day-timing
facts are tradition rule tables — emitted so §8's ladder has an internal rung,
but DivineAPI is primary for the SERVED value.
"""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from sitara_schemas.cache_keys import geohash
from sitara_schemas.facts import (
    NAKSHATRA_ORDER,
    DayTimingKind,
    DayTimingValue,
    FactKind,
    FactMethod,
    FactPrecision,
    FactSnapshot,
    FactSource,
    NakshatraBoundaryValue,
    Paksha,
    SunriseSunsetValue,
    TithiBoundaryValue,
    Tradition,
    TzMethod,
    build_fact_id,
)

from sitara_astro.engine.daytimings import DayTiming, day_timings
from sitara_astro.engine.ephemeris import data_revision, ephe_source
from sitara_astro.engine.inputs import EngineOptions, Place
from sitara_astro.engine.panchang import nakshatra_window, tithi_window
from sitara_astro.engine.riseset import SolarDay, sun_day
from sitara_astro.version import engine_semver

# The §5.5 gate for boundary times is ±2 min; the bisection resolves to 1 s and
# we state that grade honestly rather than claiming the gate (§5.3).
PRECISION_INSTANT = FactPrecision(tolerance=1.0, unit="second")

RISE_SET_CONVENTION = "upper_limb_refracted"


def panchang_subject(place: Place, tradition: Tradition) -> str:
    """The §7.2 location+tradition key, reused verbatim as the fact subject."""
    return f"{geohash(place.lat, place.lon)}-{tradition.value}"


def _tz_method(local_date: date, place: Place) -> TzMethod:
    zone = ZoneInfo(place.tz)
    noon_local = datetime.combine(local_date, time(12, 0), tzinfo=zone)
    offset = noon_local.utcoffset()
    assert offset is not None
    return TzMethod(tz=place.tz, utc_offset_seconds=int(offset.total_seconds()))


def _method(local_date: date, place: Place, tradition: Tradition, options: EngineOptions):
    return FactMethod(
        ephe_source=ephe_source(),
        node_type=options.node_type,
        rise_set=RISE_SET_CONVENTION,
        tradition=tradition,
        tz=_tz_method(local_date, place),
    )


def _snapshot(
    kind: FactKind,
    kind_path: str,
    value,  # noqa: ANN001 - the discriminated FactValue union
    *,
    local_date: date,
    subject: str,
    chart_version: int,
    method: FactMethod,
    valid_from: datetime,
    valid_to: datetime | None,
) -> FactSnapshot:
    return FactSnapshot(
        fact_id=build_fact_id(kind_path, local_date.isoformat(), subject, chart_version),
        kind=kind,
        value=value,
        precision=PRECISION_INSTANT,
        method=method,
        valid_from=valid_from,
        valid_to=valid_to,
        engine_semver=engine_semver(),
        data_revision=data_revision(),
        source=FactSource.LAYER_A,
    )


def _day_timing_path(timing: DayTiming) -> str:
    """Each window needs its own fact-ID: sixteen choghadiya parts share a kind
    but are distinct facts, so the part index joins the path."""
    if timing.part_index is None:
        return f"panchang.day_timing.{timing.timing.value}"
    return f"panchang.day_timing.{timing.timing.value}_{timing.part_index}"


def panchang_facts(
    local_date: date,
    place: Place,
    tradition: Tradition,
    options: EngineOptions,
    *,
    chart_version: int = 1,
    include_day_timings: bool = True,
) -> list[FactSnapshot]:
    """Every Layer-A panchang fact for one local date at one place.

    Raises NoRiseOrSet where the Sun does not rise or set — no sunrise means no
    honest day division, and we decline rather than invent one (§5.3).
    """
    day: SolarDay = sun_day(local_date, place)
    subject = panchang_subject(place, tradition)
    method = _method(local_date, place, tradition, options)

    def emit(kind: FactKind, path: str, value, valid_from, valid_to):  # noqa: ANN001, ANN202
        return _snapshot(
            kind,
            path,
            value,
            local_date=local_date,
            subject=subject,
            chart_version=chart_version,
            method=method,
            valid_from=valid_from,
            valid_to=valid_to,
        )

    facts = [
        emit(
            FactKind.PANCHANG_SUNRISE_SUNSET,
            "panchang.sunrise_sunset",
            SunriseSunsetValue(
                sunrise_utc=day.sunrise,
                solar_noon_utc=day.solar_noon,
                sunset_utc=day.sunset,
                next_sunrise_utc=day.next_sunrise,
            ),
            day.sunrise,
            day.next_sunrise,
        )
    ]

    # The panchang day is reckoned from sunrise, so the tithi and nakshatra
    # named for this date are the ones running AT sunrise — not at midnight.
    tithi_idx, tithi_start, tithi_end = tithi_window(day.sunrise, options.node_type)
    facts.append(
        emit(
            FactKind.PANCHANG_TITHI_BOUNDARY,
            "panchang.tithi.boundary",
            TithiBoundaryValue(
                tithi_index=tithi_idx,
                paksha=Paksha.SHUKLA if tithi_idx <= 15 else Paksha.KRISHNA,
                starts_utc=tithi_start,
                ends_utc=tithi_end,
            ),
            tithi_start,
            tithi_end,
        )
    )

    nak_idx, nak_start, nak_end = nakshatra_window(day.sunrise, options.node_type)
    facts.append(
        emit(
            FactKind.PANCHANG_NAKSHATRA_BOUNDARY,
            "panchang.nakshatra.boundary",
            NakshatraBoundaryValue(
                nakshatra=NAKSHATRA_ORDER[nak_idx],
                nakshatra_index=nak_idx + 1,
                starts_utc=nak_start,
                ends_utc=nak_end,
            ),
            nak_start,
            nak_end,
        )
    )

    if include_day_timings:
        for timing in day_timings(local_date, place):
            facts.append(
                emit(
                    FactKind.PANCHANG_DAY_TIMING,
                    _day_timing_path(timing),
                    DayTimingValue(
                        timing=DayTimingKind(timing.timing),
                        quality=timing.quality,
                        choghadiya=timing.choghadiya,
                        part_index=timing.part_index,
                        starts_utc=timing.starts_utc,
                        ends_utc=timing.ends_utc,
                    ),
                    timing.starts_utc,
                    timing.ends_utc,
                )
            )

    return facts
