"""Vendor readings → FactSnapshots (§34.2).

Layer A already emits snapshots; a vendor emits JSON. This module gives vendor
facts the same shape so that a caller — and every artefact that embeds them —
cannot tell from the structure which layer answered, only from `source`.

`data_revision` records the vendor and the fetch date rather than an ephemeris
build: a DivineAPI fact must never be mistaken for a Swiss-file computation
when a Trust Sheet is re-read months later (§5.2's provenance rule).
"""

import datetime as dt

from sitara_schemas.facts import (
    NAKSHATRA_ORDER,
    ConfidenceState,
    DayTimingValue,
    FactKind,
    FactMethod,
    FactPrecision,
    FactSnapshot,
    FactSource,
    MuhuratWindowValue,
    NakshatraBoundaryValue,
    Paksha,
    TithiBoundaryValue,
    Tradition,
    TzMethod,
    build_fact_id,
)

from sitara_api import __version__
from sitara_api.panchang.providers.base import (
    NormalisedDayTimings,
    NormalisedMuhurat,
    NormalisedPanchang,
    ProviderName,
    ResolvedPlace,
)

# A vendor states minutes, not seconds — claiming second-grade precision on a
# third-party timing would be false precision (§5.3).
PRECISION_VENDOR = FactPrecision(tolerance=60.0, unit="second")

_SOURCE_BY_PROVIDER = {
    ProviderName.DIVINEAPI: FactSource.DIVINEAPI,
    ProviderName.PROKERALA: FactSource.PROKERALA,
}


def subject_for(place: ResolvedPlace, tradition: Tradition) -> str:
    from sitara_schemas.cache_keys import geohash

    return f"{geohash(place.lat, place.lon)}-{tradition.value}"


def _method(place: ResolvedPlace, on: dt.date, tradition: Tradition) -> FactMethod:
    from zoneinfo import ZoneInfo

    noon = dt.datetime.combine(on, dt.time(12, 0), tzinfo=ZoneInfo(place.tz))
    offset = noon.utcoffset()
    assert offset is not None
    return FactMethod(
        tradition=tradition,
        tz=TzMethod(tz=place.tz, utc_offset_seconds=int(offset.total_seconds())),
    )


def _revision(provider: ProviderName, on: dt.date) -> str:
    return f"provider={provider.value};date={on.isoformat()}"


def _snapshot(
    kind: FactKind,
    kind_path: str,
    value,  # noqa: ANN001
    *,
    provider: ProviderName,
    place: ResolvedPlace,
    tradition: Tradition,
    scope_date: dt.date,
    valid_from: dt.datetime,
    valid_to: dt.datetime | None,
    chart_version: int,
    confidence: ConfidenceState | None,
) -> FactSnapshot:
    return FactSnapshot(
        fact_id=build_fact_id(
            kind_path, scope_date.isoformat(), subject_for(place, tradition), chart_version
        ),
        kind=kind,
        value=value,
        precision=PRECISION_VENDOR,
        method=_method(place, scope_date, tradition),
        valid_from=valid_from,
        valid_to=valid_to,
        engine_semver=__version__,
        data_revision=_revision(provider, scope_date),
        source=_SOURCE_BY_PROVIDER[provider],
        confidence=confidence,
    )


def panchang_facts(
    reading: NormalisedPanchang,
    place: ResolvedPlace,
    tradition: Tradition,
    *,
    chart_version: int = 1,
    confidence: ConfidenceState | None = None,
) -> list[FactSnapshot]:
    common = {
        "provider": reading.provider,
        "place": place,
        "tradition": tradition,
        "scope_date": reading.local_date,
        "chart_version": chart_version,
        "confidence": confidence,
    }
    tithi_index = reading.tithi.index
    nakshatra_index = reading.nakshatra.index
    return [
        _snapshot(
            FactKind.PANCHANG_TITHI_BOUNDARY,
            "panchang.tithi.boundary",
            TithiBoundaryValue(
                tithi_index=tithi_index,
                paksha=Paksha.SHUKLA if tithi_index <= 15 else Paksha.KRISHNA,
                starts_utc=reading.tithi.starts_utc,
                ends_utc=reading.tithi.ends_utc,
            ),
            valid_from=reading.tithi.starts_utc,
            valid_to=reading.tithi.ends_utc,
            **common,
        ),
        _snapshot(
            FactKind.PANCHANG_NAKSHATRA_BOUNDARY,
            "panchang.nakshatra.boundary",
            NakshatraBoundaryValue(
                nakshatra=NAKSHATRA_ORDER[nakshatra_index - 1],
                nakshatra_index=nakshatra_index,
                starts_utc=reading.nakshatra.starts_utc,
                ends_utc=reading.nakshatra.ends_utc,
            ),
            valid_from=reading.nakshatra.starts_utc,
            valid_to=reading.nakshatra.ends_utc,
            **common,
        ),
    ]


def day_timing_facts(
    reading: NormalisedDayTimings,
    place: ResolvedPlace,
    tradition: Tradition,
    *,
    chart_version: int = 1,
    confidence: ConfidenceState | None = None,
) -> list[FactSnapshot]:
    facts = []
    for window in reading.windows:
        suffix = f"_{window.part_index}" if window.part_index is not None else ""
        facts.append(
            _snapshot(
                FactKind.PANCHANG_DAY_TIMING,
                f"panchang.day_timing.{window.timing.value}{suffix}",
                DayTimingValue(
                    timing=window.timing,
                    quality=window.quality,
                    choghadiya=window.choghadiya,
                    part_index=window.part_index,
                    starts_utc=window.starts_utc,
                    ends_utc=window.ends_utc,
                ),
                provider=reading.provider,
                place=place,
                tradition=tradition,
                scope_date=reading.local_date,
                valid_from=window.starts_utc,
                valid_to=window.ends_utc,
                chart_version=chart_version,
                confidence=confidence,
            )
        )
    return facts


def muhurat_facts(
    reading: NormalisedMuhurat,
    place: ResolvedPlace,
    tradition: Tradition,
    scope_date: dt.date,
    *,
    chart_version: int = 1,
    confidence: ConfidenceState | None = None,
) -> list[FactSnapshot]:
    """§30.2: each window carries the city and zone it was computed FOR, so it
    can never be rendered as if it belonged to the user's own city."""
    return [
        _snapshot(
            FactKind.MUHURAT_WINDOW,
            f"muhurat.window.{reading.muhurat_type.value}_{position}",
            MuhuratWindowValue(
                muhurat_type=reading.muhurat_type,
                quality=window.quality,
                place_label=place.label,
                place_tz=place.tz,
                starts_utc=window.starts_utc,
                ends_utc=window.ends_utc,
            ),
            provider=reading.provider,
            place=place,
            tradition=tradition,
            scope_date=scope_date,
            valid_from=window.starts_utc,
            valid_to=window.ends_utc,
            chart_version=chart_version,
            confidence=confidence,
        )
        for position, window in enumerate(reading.windows, start=1)
    ]
