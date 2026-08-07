"""Parity evaluation against the SPEC §5.5 release thresholds.

    positions            ≤ 1 arc-min
    boundary times       ≤ 2 min      (tithi / nakshatra)
    dasha boundaries     ≤ 1 day
    categorical fields   exact        (rashi, nakshatra, pada, lord)

Only `verified` cases count toward the gate; `pending` cases are computed and
reported separately so the reviewer can see the engine's answers next to the
blanks they still have to fill.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel
from sitara_schemas.facts import DashaLevel, Graha

from sitara_astro.config import Settings
from sitara_astro.engine.chart import compute_natal_chart, rashi_of
from sitara_astro.engine.dasha import compute_vimshottari
from sitara_astro.engine.ephemeris import init_ephemeris
from sitara_astro.engine.inputs import EngineOptions, Place
from sitara_astro.engine.nakshatra import nakshatra_pada
from sitara_astro.engine.panchang import next_nakshatra_boundary, next_tithi_boundary
from sitara_astro.engine.transits import compute_transits
from sitara_astro.engine.tzresolve import resolve_local
from sitara_astro.golden.case import (
    DASHA_SLOTS,
    GRAHA_ORDER,
    REPO_CASES_DIR,
    CaseStatus,
    GoldenCase,
    load_all,
)

PARITY_THRESHOLD = 0.999  # §5.5: release-blocking below this on verified cases

# The engine is judged against JHora, which runs Swiss files — so must we.
init_ephemeris(Settings().resolved_swisseph_data_path)


class Dimension(StrEnum):
    POSITION = "position"
    BOUNDARY = "boundary"
    DASHA = "dasha"
    CATEGORICAL = "categorical"


TOLERANCES: dict[Dimension, tuple[float, str]] = {
    Dimension.POSITION: (1.0 / 60.0, "deg"),
    Dimension.BOUNDARY: (120.0, "s"),
    Dimension.DASHA: (86400.0, "s"),
    Dimension.CATEGORICAL: (0.0, "exact"),
}


class ComputedGraha(BaseModel):
    longitude_deg: float
    rashi: str
    nakshatra: str
    pada: int


class ComputedLagna(BaseModel):
    longitude_deg: float
    rashi: str


class ComputedDasha(BaseModel):
    lord: str
    start_utc: datetime
    end_utc: datetime


class ComputedBoundaries(BaseModel):
    moon_nakshatra_end_utc: datetime
    tithi_end_utc: datetime


class ComputedTransit(BaseModel):
    saturn_whole_sign_house: int
    moon_nakshatra: str


class ComputedCase(BaseModel):
    case_id: str
    birth_utc: datetime
    utc_offset_seconds: int
    gap_shifted_minutes: int
    ambiguous: bool
    grahas: dict[str, ComputedGraha]
    lagna: ComputedLagna
    dasha: dict[str, ComputedDasha]
    boundaries: ComputedBoundaries
    transit: ComputedTransit | None = None


def compute_case(case: GoldenCase) -> ComputedCase:
    options = EngineOptions(
        node_type=case.input.options.node_type,
        bhava_system=case.input.options.bhava_system,
        dasha_year=case.input.options.dasha_year,
        gap_policy=case.input.options.gap_policy,
    )
    resolved = resolve_local(
        case.input.date,
        case.input.time,
        case.input.tz,
        fold=case.input.fold,
        gap_policy=options.gap_policy,
    )
    place = Place(name=case.input.place, lat=case.input.lat, lon=case.input.lon, tz=case.input.tz)
    chart = compute_natal_chart(resolved, place, options)

    grahas: dict[str, ComputedGraha] = {}
    for graha in Graha:
        lon = chart.grahas[graha].longitude_deg
        _, nakshatra, pada = nakshatra_pada(lon)
        grahas[graha.value] = ComputedGraha(
            longitude_deg=lon, rashi=rashi_of(lon).value, nakshatra=nakshatra.value, pada=pada
        )

    periods = compute_vimshottari(
        chart.grahas[Graha.MOON].longitude_deg,
        resolved.utc,
        options.dasha_year,
        levels=2,
    )
    dasha: dict[str, ComputedDasha] = {}
    for slot, level in zip(DASHA_SLOTS, (DashaLevel.MAHA, DashaLevel.ANTAR), strict=True):
        running = next(
            p for p in periods if p.level is level and p.start <= resolved.utc < p.end
        )
        dasha[slot] = ComputedDasha(
            lord=running.lord.value, start_utc=running.start, end_utc=running.end
        )

    transit = None
    if case.input.transit_date_utc is not None:
        _, placements = compute_transits(chart, case.input.transit_date_utc, options)
        saturn = next(p for p in placements if p.graha is Graha.SATURN)
        moon = next(p for p in placements if p.graha is Graha.MOON)
        transit = ComputedTransit(
            saturn_whole_sign_house=saturn.whole_sign_house,
            moon_nakshatra=nakshatra_pada(moon.state.longitude_deg)[1].value,
        )

    return ComputedCase(
        case_id=case.case_id,
        birth_utc=resolved.utc,
        utc_offset_seconds=resolved.utc_offset_seconds,
        gap_shifted_minutes=resolved.gap_shifted_minutes,
        ambiguous=resolved.ambiguous,
        grahas=grahas,
        lagna=ComputedLagna(
            longitude_deg=chart.lagna_deg, rashi=chart.lagna_rashi.value
        ),
        dasha=dasha,
        boundaries=ComputedBoundaries(
            moon_nakshatra_end_utc=next_nakshatra_boundary(resolved.utc, options.node_type),
            tithi_end_utc=next_tithi_boundary(resolved.utc, options.node_type),
        ),
        transit=transit,
    )


@dataclass(frozen=True)
class Check:
    case_id: str
    dimension: Dimension
    field: str
    expected: str
    actual: str
    delta: float | None
    tolerance: float
    unit: str
    passed: bool

    def describe(self) -> str:
        if self.dimension is Dimension.CATEGORICAL:
            return f"{self.case_id} {self.field}: expected {self.expected}, got {self.actual}"
        shown = _human_delta(self.dimension, self.delta or 0.0)
        return (
            f"{self.case_id} {self.field}: expected {self.expected}, got {self.actual} "
            f"(Δ {shown})"
        )


def _human_delta(dimension: Dimension, delta: float) -> str:
    if dimension is Dimension.POSITION:
        return f"{delta * 60:.2f} arc-min"
    if dimension is Dimension.DASHA:
        return f"{delta / 86400:.2f} day"
    return f"{delta:.1f} s"


@dataclass(frozen=True)
class CaseEvaluation:
    case_id: str
    status: CaseStatus
    checks: list[Check]
    error: str | None = None

    @property
    def total(self) -> int:
        return len(self.checks)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.passed]


def _angular_delta(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def _numeric_check(
    case_id: str, dimension: Dimension, field: str, expected, actual, delta: float
) -> Check:  # noqa: ANN001
    tolerance, unit = TOLERANCES[dimension]
    return Check(
        case_id=case_id,
        dimension=dimension,
        field=field,
        expected=str(expected),
        actual=str(actual),
        delta=delta,
        tolerance=tolerance,
        unit=unit,
        passed=delta <= tolerance,
    )


def _categorical_check(case_id: str, field: str, expected, actual) -> Check:  # noqa: ANN001
    expected_value = getattr(expected, "value", expected)
    return Check(
        case_id=case_id,
        dimension=Dimension.CATEGORICAL,
        field=field,
        expected=str(expected_value),
        actual=str(actual),
        delta=None,
        tolerance=0.0,
        unit="exact",
        passed=str(expected_value) == str(actual),
    )


def evaluate_case(case: GoldenCase, computed: ComputedCase) -> CaseEvaluation:
    """Compare filled expectations against computed values. Unfilled
    (NEEDS_VERIFICATION) fields produce no checks — they are not failures."""
    checks: list[Check] = []
    cid = case.case_id

    for name in GRAHA_ORDER:
        expectation, actual = case.expected.grahas[name], computed.grahas[name]
        if expectation.longitude_deg is not None:
            checks.append(
                _numeric_check(
                    cid,
                    Dimension.POSITION,
                    f"grahas.{name}.longitude_deg",
                    f"{expectation.longitude_deg:.4f}",
                    f"{actual.longitude_deg:.4f}",
                    _angular_delta(expectation.longitude_deg, actual.longitude_deg),
                )
            )
        for attr in ("rashi", "nakshatra", "pada"):
            if getattr(expectation, attr) is not None:
                checks.append(
                    _categorical_check(
                        cid, f"grahas.{name}.{attr}", getattr(expectation, attr),
                        getattr(actual, attr),
                    )
                )

    if case.expected.lagna.longitude_deg is not None:
        checks.append(
            _numeric_check(
                cid,
                Dimension.POSITION,
                "lagna.longitude_deg",
                f"{case.expected.lagna.longitude_deg:.4f}",
                f"{computed.lagna.longitude_deg:.4f}",
                _angular_delta(case.expected.lagna.longitude_deg, computed.lagna.longitude_deg),
            )
        )
    if case.expected.lagna.rashi is not None:
        checks.append(
            _categorical_check(cid, "lagna.rashi", case.expected.lagna.rashi, computed.lagna.rashi)
        )

    for slot in DASHA_SLOTS:
        expectation, actual = case.expected.dasha[slot], computed.dasha[slot]
        if expectation.lord is not None:
            checks.append(
                _categorical_check(cid, f"dasha.{slot}.lord", expectation.lord, actual.lord)
            )
        for bound, actual_dt in (("start", actual.start_utc), ("end", actual.end_utc)):
            expected_date: date | None = getattr(expectation, bound)
            if expected_date is None:
                continue
            expected_dt = datetime.combine(expected_date, time.min, tzinfo=UTC)
            checks.append(
                _numeric_check(
                    cid,
                    Dimension.DASHA,
                    f"dasha.{slot}.{bound}",
                    expected_date.isoformat(),
                    actual_dt.isoformat(),
                    abs((actual_dt - expected_dt).total_seconds()),
                )
            )

    for attr in ("moon_nakshatra_end_utc", "tithi_end_utc"):
        expected_dt = getattr(case.expected.boundaries, attr)
        if expected_dt is None:
            continue
        actual_dt = getattr(computed.boundaries, attr)
        checks.append(
            _numeric_check(
                cid,
                Dimension.BOUNDARY,
                f"boundaries.{attr}",
                expected_dt.isoformat(),
                actual_dt.isoformat(),
                abs((actual_dt - expected_dt).total_seconds()),
            )
        )

    if case.expected.transit is not None and computed.transit is not None:
        for attr in ("saturn_whole_sign_house", "moon_nakshatra"):
            expected_value = getattr(case.expected.transit, attr)
            if expected_value is not None:
                checks.append(
                    _categorical_check(
                        cid, f"transit.{attr}", expected_value, getattr(computed.transit, attr)
                    )
                )

    return CaseEvaluation(case_id=cid, status=case.status, checks=checks)


@dataclass(frozen=True)
class ParityReport:
    evaluations: list[CaseEvaluation]

    @property
    def verified(self) -> list[CaseEvaluation]:
        return [e for e in self.evaluations if e.status is CaseStatus.VERIFIED]

    @property
    def pending(self) -> list[CaseEvaluation]:
        return [e for e in self.evaluations if e.status is CaseStatus.PENDING]

    @property
    def verified_total(self) -> int:
        return len(self.verified)

    @property
    def pending_total(self) -> int:
        return len(self.pending)

    @property
    def checks_total(self) -> int:
        return sum(e.total for e in self.verified)

    @property
    def checks_passed(self) -> int:
        return sum(e.passed for e in self.verified)

    @property
    def parity(self) -> float | None:
        """None until a verified case carries at least one filled expectation."""
        return self.checks_passed / self.checks_total if self.checks_total else None

    @property
    def failures(self) -> list[Check]:
        return [c for e in self.verified for c in e.failures]

    @property
    def meets_gate(self) -> bool:
        # An engine crash on any case is a gate failure, not an absent check.
        if self.errors:
            return False
        return self.parity is None or self.parity >= PARITY_THRESHOLD

    @property
    def errors(self) -> list[CaseEvaluation]:
        return [e for e in self.evaluations if e.error]

    def render(self) -> str:
        lines = [
            "=" * 72,
            "GOLDEN-SET PARITY REPORT (SPEC §5.5)",
            "=" * 72,
            f"cases: {len(self.evaluations)}  "
            f"verified: {self.verified_total}  pending: {self.pending_total}",
            "",
            "Thresholds  position ≤1 arc-min · boundary ≤2 min · dasha ≤1 day · categorical exact",
            "",
            f"{'dimension':<14}{'checks':>8}{'passed':>8}{'failed':>8}   tolerance",
        ]
        for dimension in Dimension:
            checks = [c for e in self.verified for c in e.checks if c.dimension is dimension]
            passed = sum(1 for c in checks if c.passed)
            tolerance, unit = TOLERANCES[dimension]
            shown = "exact" if unit == "exact" else _human_delta(dimension, tolerance)
            lines.append(
                f"{dimension.value:<14}{len(checks):>8}{passed:>8}"
                f"{len(checks) - passed:>8}   {shown}"
            )

        lines += ["", f"verified checks: {self.checks_passed}/{self.checks_total}"]
        if self.parity is None:
            lines.append(
                "PARITY: n/a — no verified expectations yet. The gate arms on the "
                "Jyotish lead's first sign-off."
            )
        else:
            verdict = "PASS" if self.meets_gate else "FAIL"
            lines.append(
                f"PARITY: {self.parity:.4%}  (gate ≥ {PARITY_THRESHOLD:.1%})  → {verdict}"
            )

        if self.failures:
            lines += ["", f"FAILURES ({len(self.failures)}):"]
            lines += [f"  ✗ {c.describe()}" for c in self.failures[:40]]
            if len(self.failures) > 40:
                lines.append(f"  … and {len(self.failures) - 40} more")

        if self.pending:
            unfilled = sum(1 for e in self.pending if e.total == 0)
            lines += [
                "",
                f"PENDING ({self.pending_total} cases, not gated): "
                f"{unfilled} awaiting all expected values; "
                f"{self.pending_total - unfilled} partially filled.",
            ]
            partial = [(e.case_id, e.passed, e.total) for e in self.pending if e.total]
            lines += [f"  · {cid}: {ok}/{tot} filled checks pass" for cid, ok, tot in partial[:20]]

        if self.errors:
            lines += ["", f"ERRORS ({len(self.errors)}):"]
            lines += [f"  ! {e.case_id}: {e.error}" for e in self.errors]
        lines.append("=" * 72)
        return "\n".join(lines)


def build_report(cases_dir: Path = REPO_CASES_DIR) -> ParityReport:
    evaluations: list[CaseEvaluation] = []
    for case in load_all(cases_dir):
        try:
            evaluations.append(evaluate_case(case, compute_case(case)))
        except Exception as exc:  # engine failure is a reportable case outcome
            evaluations.append(
                CaseEvaluation(
                    case_id=case.case_id,
                    status=case.status,
                    checks=[],
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
    return ParityReport(evaluations=evaluations)
