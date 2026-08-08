"""Panchang parity — §5.5's ≤2 min boundary threshold, ≥99.9% gate.

Verified cases gate; pending cases are computed and reported but never block a
release. So the moment the Jyotish lead signs off PC-001, the gate arms — no
further wiring, which is the whole point of doing this before the values exist.

Engine output is UTC; expectations are LOCAL (see panchang_case). The
comparison converts ours to theirs rather than the reverse, so a failure
message reads in the same clock the reviewer used.
"""

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from sitara_schemas.facts import (
    DayTimingKind,
    FactKind,
    NakshatraBoundaryValue,
    Paksha,
    TithiBoundaryValue,
)

from sitara_astro.engine.daytimings import day_timings
from sitara_astro.engine.inputs import EngineOptions, Place
from sitara_astro.engine.panchang_factbuild import panchang_facts
from sitara_astro.engine.riseset import sun_day
from sitara_astro.golden.case import CaseStatus
from sitara_astro.golden.panchang_case import (
    REPO_PANCHANG_DIR,
    TARGET_CASE_COUNT,
    PanchangCase,
    load_all,
    parse_local,
)
from sitara_astro.golden.parity import (
    PARITY_THRESHOLD,
    Check,
    Dimension,
    _numeric_check,
)

PANCHANG_PARITY_THRESHOLD = PARITY_THRESHOLD  # §5.5: same 99.9% as astrology

_BAND_KINDS = {
    "rahu_kaal": DayTimingKind.RAHU_KAAL,
    "yamaganda": DayTimingKind.YAMAGANDA,
    "gulikai": DayTimingKind.GULIKAI,
    "abhijit": DayTimingKind.ABHIJIT,
}


def _place(case: PanchangCase) -> Place:
    return Place(
        name=case.input.place, lat=case.input.lat, lon=case.input.lon, tz=case.input.tz
    )


def _categorical(case_id: str, field: str, expected: object, actual: object) -> Check:
    return Check(
        case_id=case_id,
        dimension=Dimension.CATEGORICAL,
        field=field,
        expected=str(expected),
        actual=str(actual),
        delta=None,
        tolerance=0.0,
        unit="exact",
        passed=str(expected).strip().lower() == str(actual).strip().lower(),
    )


def _instant(case: PanchangCase, field: str, expected_local: str, actual_utc: dt.datetime) -> Check:
    """Compare an engine instant against a reviewer's local-time expectation."""
    zone = ZoneInfo(case.input.tz)
    expected = parse_local(expected_local, case)
    actual_local = actual_utc.astimezone(zone)
    delta = abs((actual_local - expected).total_seconds())
    return _numeric_check(
        case.case_id,
        Dimension.BOUNDARY,
        field,
        expected.strftime("%Y-%m-%d %H:%M:%S"),
        actual_local.strftime("%Y-%m-%d %H:%M:%S"),
        delta,
    )


def evaluate_case(case: PanchangCase) -> list[Check]:
    """Filled expectations produce checks; unfilled ones produce none — they
    are work the reviewer has not done, not failures."""
    checks: list[Check] = []
    place = _place(case)
    options = EngineOptions()
    expected = case.expected

    # tz provenance is asserted every run, independent of astrology (§5.2).
    if case.tz_expected.utc_offset is not None:
        noon = dt.datetime.combine(
            case.input.local_date, dt.time(12, 0), tzinfo=ZoneInfo(case.input.tz)
        )
        offset = noon.utcoffset()
        assert offset is not None
        total = int(offset.total_seconds())
        sign = "+" if total >= 0 else "-"
        actual = f"{sign}{abs(total) // 3600:02d}:{(abs(total) % 3600) // 60:02d}"
        checks.append(
            _categorical(case.case_id, "tz.utc_offset", case.tz_expected.utc_offset, actual)
        )

    day = sun_day(case.input.local_date, place)

    for field, actual in (
        ("sun.sunrise_local", day.sunrise),
        ("sun.sunset_local", day.sunset),
        ("sun.solar_noon_local", day.solar_noon),
    ):
        value = getattr(expected.sun, field.split(".")[1])
        if value is not None:
            checks.append(_instant(case, field, value, actual))

    facts = {
        f.kind: f
        for f in panchang_facts(
            case.input.local_date, place, case.input.tradition, options,
            include_day_timings=False,
        )
    }
    tithi = facts[FactKind.PANCHANG_TITHI_BOUNDARY].value
    nakshatra = facts[FactKind.PANCHANG_NAKSHATRA_BOUNDARY].value
    # FactValue is a discriminated union; narrow it rather than suppressing —
    # a kind/value mismatch would be a real contract bug, not a typing nuisance.
    assert isinstance(tithi, TithiBoundaryValue)
    assert isinstance(nakshatra, NakshatraBoundaryValue)

    if expected.tithi.index_at_sunrise is not None:
        checks.append(
            _categorical(
                case.case_id,
                "tithi.index_at_sunrise",
                expected.tithi.index_at_sunrise,
                tithi.tithi_index,
            )
        )
    if expected.tithi.paksha is not None:
        checks.append(
            _categorical(
                case.case_id,
                "tithi.paksha",
                expected.tithi.paksha,
                Paksha(tithi.paksha).value,
            )
        )
    for field, attribute in (
        ("tithi.starts_local", "starts_utc"),
        ("tithi.ends_local", "ends_utc"),
    ):
        value = getattr(expected.tithi, field.split(".")[1])
        if value is not None:
            checks.append(_instant(case, field, value, getattr(tithi, attribute)))

    if expected.nakshatra.name_at_sunrise is not None:
        checks.append(
            _categorical(
                case.case_id,
                "nakshatra.name_at_sunrise",
                expected.nakshatra.name_at_sunrise,
                nakshatra.nakshatra.value,
            )
        )
    for field, attribute in (
        ("nakshatra.starts_local", "starts_utc"),
        ("nakshatra.ends_local", "ends_utc"),
    ):
        value = getattr(expected.nakshatra, field.split(".")[1])
        if value is not None:
            checks.append(_instant(case, field, value, getattr(nakshatra, attribute)))

    # --- tradition rule tables (§8 fallback rung; Jyotish-adjudicable)
    timings = day_timings(case.input.local_date, place)
    by_kind = {t.timing: t for t in timings if t.part_index is None}
    for band, kind in _BAND_KINDS.items():
        band_expected = getattr(expected.day_timings, band)
        actual = by_kind.get(kind)
        if actual is None:  # pragma: no cover - every band is always emitted
            continue
        for suffix, attribute in (("starts_local", "starts_utc"), ("ends_local", "ends_utc")):
            value = getattr(band_expected, suffix)
            if value is not None:
                checks.append(
                    _instant(
                        case,
                        f"day_timings.{band}.{suffix}",
                        value,
                        getattr(actual, attribute),
                    )
                )

    for field, kind in (
        ("first_day_part", DayTimingKind.CHOGHADIYA_DAY),
        ("first_night_part", DayTimingKind.CHOGHADIYA_NIGHT),
    ):
        value = getattr(expected.choghadiya, field)
        if value is None:
            continue
        parts = sorted(
            (t for t in timings if t.timing is kind), key=lambda t: t.starts_utc
        )
        first = parts[0].choghadiya
        checks.append(
            _categorical(
                case.case_id,
                f"choghadiya.{field}",
                value,
                first.value if first else "none",
            )
        )

    return checks


@dataclass(frozen=True)
class PanchangEvaluation:
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


@dataclass(frozen=True)
class PanchangReport:
    evaluations: list[PanchangEvaluation]

    @property
    def verified(self) -> list[PanchangEvaluation]:
        return [e for e in self.evaluations if e.status is CaseStatus.VERIFIED]

    @property
    def pending(self) -> list[PanchangEvaluation]:
        return [e for e in self.evaluations if e.status is CaseStatus.PENDING]

    @property
    def checks_total(self) -> int:
        return sum(e.total for e in self.verified)

    @property
    def checks_passed(self) -> int:
        return sum(e.passed for e in self.verified)

    @property
    def parity(self) -> float | None:
        return self.checks_passed / self.checks_total if self.checks_total else None

    @property
    def failures(self) -> list[Check]:
        return [c for e in self.verified for c in e.failures]

    @property
    def errors(self) -> list[PanchangEvaluation]:
        return [e for e in self.evaluations if e.error]

    @property
    def meets_gate(self) -> bool:
        if self.errors:
            return False
        return self.parity is None or self.parity >= PANCHANG_PARITY_THRESHOLD

    def render(self) -> str:
        lines = [
            "=" * 72,
            "PANCHANG PARITY REPORT (SPEC §5.2 Layer C — boundaries ≤2 min)",
            "=" * 72,
            f"cases: {len(self.evaluations)}/{TARGET_CASE_COUNT} target  "
            f"verified: {len(self.verified)}  pending: {len(self.pending)}",
            "",
            "Astronomy (sun/tithi/nakshatra) — Layer A authoritative (§35.3).",
            "Day timings + choghadiya — tradition tables; a failure may be the "
            "TABLE, not the maths.",
            "",
            f"verified checks: {self.checks_passed}/{self.checks_total}",
        ]
        if self.parity is None:
            lines.append(
                "PARITY: n/a — no verified expectations yet. The gate arms on the "
                "reviewer's first sign-off."
            )
        else:
            verdict = "PASS" if self.meets_gate else "FAIL"
            lines.append(
                f"PARITY: {self.parity:.4%}  (gate ≥ {PANCHANG_PARITY_THRESHOLD:.1%})  → {verdict}"
            )
        if self.failures:
            lines += ["", f"FAILURES ({len(self.failures)}):"]
            lines += [f"  ✗ {c.describe()}" for c in self.failures[:40]]
        if self.pending:
            lines += [
                "",
                f"PENDING ({len(self.pending)} cases, not gated) — "
                f"{TARGET_CASE_COUNT - len(self.evaluations)} more cases to author.",
            ]
        if self.errors:
            lines += ["", f"ERRORS ({len(self.errors)}):"]
            lines += [f"  ! {e.case_id}: {e.error}" for e in self.errors]
        lines.append("=" * 72)
        return "\n".join(lines)


def build_report(cases_dir: Path | str = REPO_PANCHANG_DIR) -> PanchangReport:
    evaluations: list[PanchangEvaluation] = []
    for case in load_all(cases_dir):
        try:
            evaluations.append(PanchangEvaluation(case.case_id, case.status, evaluate_case(case)))
        except Exception as exc:
            evaluations.append(
                PanchangEvaluation(
                    case.case_id, case.status, [], error=f"{type(exc).__name__}: {exc}"
                )
            )
    return PanchangReport(evaluations=evaluations)
