"""FactSnapshot emission (SPEC §34.2).

Owns the fact-ID grammar, method provenance, precision constants and validity
windows. Fact-IDs are logical keys; callers embed the returned snapshots in
full inside every citing artefact — there is deliberately no facts collection.
"""

from datetime import date, timedelta

from sitara_schemas.facts import (
    RASHI_ORDER,
    DashaPeriodValue,
    FactKind,
    FactMethod,
    FactPrecision,
    FactSnapshot,
    Graha,
    GrahaPositionValue,
    HouseAssignmentValue,
    HouseCuspsValue,
    LagnaValue,
    NakshatraValue,
    TzMethod,
    build_fact_id,
)

from sitara_astro.engine.chart import (
    NatalChart,
    bhava_of,
    compute_natal_chart,
    rashi_of,
    whole_sign_house,
)
from sitara_astro.engine.dasha import compute_vimshottari
from sitara_astro.engine.ephemeris import data_revision, ephe_source
from sitara_astro.engine.inputs import BirthDetails, EngineOptions
from sitara_astro.engine.nakshatra import nakshatra_pada
from sitara_astro.engine.transits import compute_transits
from sitara_astro.engine.tzresolve import ResolvedInstant, resolve_local
from sitara_astro.version import engine_semver

# Stated precision, never false precision (§5.3): positions carry the engine's
# 1 arc-sec computational grade (the §5.5 GATE is looser: 1 arc-min); dasha
# boundaries are day-grade by convention.
PRECISION_POSITION = FactPrecision(tolerance=1.0, unit="arc_sec")
PRECISION_DASHA = FactPrecision(tolerance=1.0, unit="day")
PRECISION_HOUSE = FactPrecision(tolerance=1.0, unit="arc_sec")


def _tz_method(resolved: ResolvedInstant) -> TzMethod:
    return TzMethod(
        tz=resolved.tz,
        utc_offset_seconds=resolved.utc_offset_seconds,
        fold_used=resolved.fold_used,  # type: ignore[arg-type]
        ambiguous=resolved.ambiguous,
        gap_shifted_minutes=resolved.gap_shifted_minutes,
    )


def _resolve_birth(birth: BirthDetails, options: EngineOptions) -> ResolvedInstant:
    return resolve_local(
        birth.date, birth.time, birth.place.tz, fold=birth.fold, gap_policy=options.gap_policy
    )


def _natal_chart(birth: BirthDetails, options: EngineOptions) -> NatalChart:
    return compute_natal_chart(_resolve_birth(birth, options), birth.place, options)


def natal_facts(
    birth: BirthDetails, options: EngineOptions, *, subject: str, chart_version: int
) -> list[FactSnapshot]:
    """29 facts: 9 positions + 9 nakshatras + lagna + house cusps + 9 house placements."""
    chart = _natal_chart(birth, options)
    born = chart.resolved.utc
    tz = _tz_method(chart.resolved)
    method_position = FactMethod(
        ayanamsa="lahiri", ephe_source=ephe_source(), node_type=options.node_type, tz=tz
    )
    method_houses = FactMethod(
        ayanamsa="lahiri",
        ephe_source=ephe_source(),
        node_type=options.node_type,
        house_presentation="whole_sign",
        bhava_system=options.bhava_system,
        tz=tz,
    )
    common = {
        "valid_from": born,
        "valid_to": None,
        "engine_semver": engine_semver(),
        "data_revision": data_revision(),
    }

    facts: list[FactSnapshot] = []
    lagna_idx = RASHI_ORDER.index(chart.lagna_rashi)
    for graha, state in chart.grahas.items():
        lon = state.longitude_deg
        nak_index, nak, pada = nakshatra_pada(lon)
        facts.append(
            FactSnapshot(
                fact_id=build_fact_id(
                    f"natal.{graha.value}.position", "natal", subject, chart_version
                ),
                kind=FactKind.NATAL_GRAHA_POSITION,
                value=GrahaPositionValue(
                    graha=graha,
                    longitude_deg=lon,
                    rashi=rashi_of(lon),
                    degrees_in_rashi=lon % 30.0,
                    speed_deg_per_day=state.speed_deg_per_day,
                    retrograde=state.speed_deg_per_day < 0,
                ),
                precision=PRECISION_POSITION,
                method=method_position,
                **common,
            )
        )
        facts.append(
            FactSnapshot(
                fact_id=build_fact_id(
                    f"natal.{graha.value}.nakshatra", "natal", subject, chart_version
                ),
                kind=FactKind.NATAL_GRAHA_NAKSHATRA,
                value=NakshatraValue(
                    graha=graha, nakshatra=nak, nakshatra_index=nak_index, pada=pada
                ),
                precision=PRECISION_POSITION,
                method=method_position,
                **common,
            )
        )
        facts.append(
            FactSnapshot(
                fact_id=build_fact_id(
                    f"natal.{graha.value}.house", "natal", subject, chart_version
                ),
                kind=FactKind.NATAL_GRAHA_HOUSE,
                value=HouseAssignmentValue(
                    graha=graha,
                    whole_sign_house=whole_sign_house(RASHI_ORDER.index(rashi_of(lon)), lagna_idx),
                    bhava=bhava_of(lon, chart.sandhi_deg),
                ),
                precision=PRECISION_HOUSE,
                method=method_houses,
                **common,
            )
        )
    facts.append(
        FactSnapshot(
            fact_id=build_fact_id("natal.lagna", "natal", subject, chart_version),
            kind=FactKind.NATAL_LAGNA,
            value=LagnaValue(longitude_deg=chart.lagna_deg, rashi=chart.lagna_rashi),
            precision=PRECISION_POSITION,
            method=method_position,
            **common,
        )
    )
    facts.append(
        FactSnapshot(
            fact_id=build_fact_id("natal.house.cusps", "natal", subject, chart_version),
            kind=FactKind.NATAL_HOUSE_CUSPS,
            value=HouseCuspsValue(
                system=options.bhava_system,
                madhya_deg=chart.madhya_deg,
                sandhi_deg=chart.sandhi_deg,
            ),
            precision=PRECISION_HOUSE,
            method=method_houses,
            **common,
        )
    )
    return facts


def dasha_facts(
    birth: BirthDetails,
    options: EngineOptions,
    *,
    subject: str,
    chart_version: int,
    levels: int = 3,
) -> list[FactSnapshot]:
    """Full vimshottari cycle (9 maha + 81 antar + 729 pratyantar at depth 3)."""
    chart = _natal_chart(birth, options)
    moon = chart.grahas[Graha.MOON].longitude_deg
    periods = compute_vimshottari(moon, chart.resolved.utc, options.dasha_year, levels=levels)
    method = FactMethod(
        ayanamsa="lahiri",
        ephe_source=ephe_source(),
        dasha_year=options.dasha_year,
        tz=_tz_method(chart.resolved),
    )
    return [
        FactSnapshot(
            fact_id=build_fact_id(
                f"dasha.vimshottari.{p.level.value}.{p.lord.value}",
                p.start.date().isoformat(),
                subject,
                chart_version,
            ),
            kind=FactKind.DASHA_VIMSHOTTARI_PERIOD,
            value=DashaPeriodValue(
                level=p.level, lord=p.lord, start_utc=p.start, end_utc=p.end, parent_lords=p.parents
            ),
            precision=PRECISION_DASHA,
            method=method,
            valid_from=p.start,
            valid_to=p.end,
            engine_semver=engine_semver(),
            data_revision=data_revision(),
        )
        for p in periods
    ]


def transit_facts(
    birth: BirthDetails,
    options: EngineOptions,
    on_date: date,
    *,
    subject: str,
    chart_version: int,
) -> list[FactSnapshot]:
    """18 facts: 9 positions (point-valid at 00:00 UTC) + 9 house placements
    (valid for the UTC day) relative to the natal chart."""
    chart = _natal_chart(birth, options)
    instant, placements = compute_transits(chart, on_date, options)
    scope = on_date.isoformat()
    method_position = FactMethod(
        ayanamsa="lahiri", ephe_source=ephe_source(), node_type=options.node_type
    )
    method_house = FactMethod(
        ayanamsa="lahiri",
        ephe_source=ephe_source(),
        node_type=options.node_type,
        house_presentation="whole_sign",
        bhava_system=options.bhava_system,
    )
    facts: list[FactSnapshot] = []
    for placement in placements:
        lon = placement.state.longitude_deg
        facts.append(
            FactSnapshot(
                fact_id=build_fact_id(
                    f"transit.{placement.graha.value}.position", scope, subject, chart_version
                ),
                kind=FactKind.TRANSIT_GRAHA_POSITION,
                value=GrahaPositionValue(
                    graha=placement.graha,
                    longitude_deg=lon,
                    rashi=rashi_of(lon),
                    degrees_in_rashi=lon % 30.0,
                    speed_deg_per_day=placement.state.speed_deg_per_day,
                    retrograde=placement.state.speed_deg_per_day < 0,
                ),
                precision=PRECISION_POSITION,
                method=method_position,
                valid_from=instant,
                valid_to=instant,  # point-valid
                engine_semver=engine_semver(),
                data_revision=data_revision(),
            )
        )
        facts.append(
            FactSnapshot(
                fact_id=build_fact_id(
                    f"transit.{placement.graha.value}.house", scope, subject, chart_version
                ),
                kind=FactKind.TRANSIT_GRAHA_HOUSE,
                value=HouseAssignmentValue(
                    graha=placement.graha,
                    whole_sign_house=placement.whole_sign_house,
                    bhava=placement.bhava,
                ),
                precision=PRECISION_HOUSE,
                method=method_house,
                valid_from=instant,
                valid_to=instant + timedelta(days=1),  # UTC-day-valid
                engine_semver=engine_semver(),
                data_revision=data_revision(),
            )
        )
    return facts
