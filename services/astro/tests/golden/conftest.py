"""Golden-set harness fixtures (SPEC §5.5, golden-set/cases/README.md).

Drives the engine DIRECTLY (no HTTP) so the golden signal is pure engine.
Structure assertions run for every case; parity assertions apply only to
`status: verified` cases, which only a named human may create.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import cache

import pytest
from sitara_schemas.facts import FactKind, FactSnapshot, Graha

from sitara_astro.config import Settings
from sitara_astro.engine.ephemeris import init_ephemeris
from sitara_astro.engine.factbuild import dasha_facts, natal_facts, transit_facts
from sitara_astro.engine.inputs import BirthDetails, EngineOptions, Place
from sitara_astro.golden.case import REPO_CASES_DIR, CaseStatus, GoldenCase, load_all

# Golden parity is judged against JHora, which runs Swiss files — so must we.
init_ephemeris(Settings().resolved_swisseph_data_path)

CASES_DIR = REPO_CASES_DIR
ALL_CASES: list[GoldenCase] = load_all(CASES_DIR)
VERIFIED_CASES = [c for c in ALL_CASES if c.status is CaseStatus.VERIFIED]

ARC_MIN_DEG = 1.0 / 60.0
DASHA_TOLERANCE = timedelta(days=1)
BOUNDARY_TOLERANCE = timedelta(minutes=2)


def birth_of(case: GoldenCase) -> BirthDetails:
    return BirthDetails(
        date=case.input.date,
        time=case.input.time,
        fold=case.input.fold,
        place=Place(
            name=case.input.place, lat=case.input.lat, lon=case.input.lon, tz=case.input.tz
        ),
    )


def options_of(case: GoldenCase) -> EngineOptions:
    return EngineOptions(
        node_type=case.input.options.node_type,
        bhava_system=case.input.options.bhava_system,
        dasha_year=case.input.options.dasha_year,
        gap_policy=case.input.options.gap_policy,
    )


def expected_utc_offset_seconds(case: GoldenCase) -> int:
    text = case.tz_expected.utc_offset
    sign = 1 if text[0] == "+" else -1
    hours, minutes = text[1:].split(":")
    return sign * (int(hours) * 3600 + int(minutes) * 60)


def expected_birth_utc(case: GoldenCase) -> datetime:
    """Birth instant per tz_expected: wall time (+ any gap shift) - offset."""
    local = datetime.combine(case.input.date, case.input.time) + timedelta(
        minutes=case.tz_expected.gap_shifted_minutes
    )
    return (local - timedelta(seconds=expected_utc_offset_seconds(case))).replace(tzinfo=UTC)


@dataclass(frozen=True)
class CaseResult:
    natal: tuple[FactSnapshot, ...]
    dasha: tuple[FactSnapshot, ...]
    transit: tuple[FactSnapshot, ...]

    def natal_of(self, kind: FactKind, graha: Graha | None = None) -> FactSnapshot:
        matches = [
            f
            for f in self.natal
            if f.kind is kind and (graha is None or getattr(f.value, "graha", None) is graha)
        ]
        assert len(matches) == 1, f"expected exactly one {kind}/{graha}, got {len(matches)}"
        return matches[0]


@cache
def run_case(case_id: str) -> CaseResult:
    case = next(c for c in ALL_CASES if c.case_id == case_id)
    birth, options = birth_of(case), options_of(case)
    subject, version = f"golden-{case.case_id.lower()}", 1
    natal = natal_facts(birth, options, subject=subject, chart_version=version)
    dasha = dasha_facts(birth, options, subject=subject, chart_version=version)
    transit: list[FactSnapshot] = []
    if case.input.transit_date_utc is not None:
        transit = transit_facts(
            birth, options, case.input.transit_date_utc, subject=subject, chart_version=version
        )
    return CaseResult(tuple(natal), tuple(dasha), tuple(transit))


def angular_delta(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


@pytest.fixture(params=ALL_CASES, ids=lambda c: c.case_id)
def case(request: pytest.FixtureRequest) -> GoldenCase:
    return request.param


@pytest.fixture()
def result(case: GoldenCase) -> CaseResult:
    return run_case(case.case_id)
