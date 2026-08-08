"""Parity evaluation against the §5.5 thresholds.

Thresholds under test: positions ≤1 arc-min · boundary times ≤2 min ·
dasha boundaries ≤1 day · categorical fields exact. Only `verified` cases
count toward the gate; `pending` cases are evaluated and reported separately.
"""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from sitara_astro.golden.case import CaseStatus, load_case, save_case, set_field
from sitara_astro.golden.parity import (
    PARITY_THRESHOLD,
    Dimension,
    build_report,
    compute_case,
    evaluate_case,
)

CASES_DIR = Path(__file__).resolve().parents[4] / "golden-set" / "cases"


@pytest.fixture(scope="module")
def gc001():  # noqa: ANN201
    return load_case(CASES_DIR / "GC-001.yaml")


@pytest.fixture(scope="module")
def gc001_computed(gc001):  # noqa: ANN001, ANN201
    return compute_case(gc001)


def _fields(evaluation, suffix: str):  # noqa: ANN001, ANN201
    return [c for c in evaluation.checks if c.field.endswith(suffix)]


def _one(evaluation, suffix: str):  # noqa: ANN001, ANN201
    return next(c for c in evaluation.checks if c.field.endswith(suffix))


def verified(case):  # noqa: ANN001, ANN201
    return case.model_copy(
        update={
            "status": CaseStatus.VERIFIED,
            "verified_by": "Test Reviewer",
            "verified_on": date(2026, 8, 7),
            "source": "JHora",
        }
    )


class TestThresholds:
    def test_position_within_one_arc_min_passes(self, gc001, gc001_computed) -> None:  # noqa: ANN001
        actual = gc001_computed.grahas["sun"].longitude_deg
        case = verified(set_field(gc001, "grahas.sun.longitude_deg", f"{actual + 0.9 / 60:.6f}"))
        checks = _fields(evaluate_case(case, gc001_computed), "sun.longitude_deg")
        assert len(checks) == 1 and checks[0].passed

    def test_position_beyond_one_arc_min_fails(self, gc001, gc001_computed) -> None:  # noqa: ANN001
        actual = gc001_computed.grahas["sun"].longitude_deg
        case = verified(set_field(gc001, "grahas.sun.longitude_deg", f"{actual + 1.1 / 60:.6f}"))
        check = _one(evaluate_case(case, gc001_computed), "sun.longitude_deg")
        assert not check.passed
        assert check.dimension is Dimension.POSITION

    def test_position_wraps_across_zero(self, gc001, gc001_computed) -> None:  # noqa: ANN001
        """359.99° vs 0.01° is a 0.02° gap, not 359.98°."""
        computed = gc001_computed.model_copy(deep=True)
        computed.grahas["sun"].longitude_deg = 359.995
        case = verified(set_field(gc001, "grahas.sun.longitude_deg", "0.005"))
        check = _one(evaluate_case(case, computed), "sun.longitude_deg")
        assert check.passed

    def test_dasha_boundary_one_day_tolerance(self, gc001, gc001_computed) -> None:  # noqa: ANN001
        actual_start = gc001_computed.dasha["maha_at_birth"].start_utc
        within = (actual_start.date()).isoformat()
        case = verified(set_field(gc001, "dasha.maha_at_birth.start", within))
        check = _one(evaluate_case(case, gc001_computed), "maha_at_birth.start")
        assert check.passed
        assert check.dimension is Dimension.DASHA

    def test_dasha_boundary_beyond_one_day_fails(self, gc001, gc001_computed) -> None:  # noqa: ANN001
        actual_start = gc001_computed.dasha["maha_at_birth"].start_utc
        far = date.fromordinal(actual_start.date().toordinal() + 3).isoformat()
        case = verified(set_field(gc001, "dasha.maha_at_birth.start", far))
        check = _one(evaluate_case(case, gc001_computed), "maha_at_birth.start")
        assert not check.passed

    def test_boundary_time_two_minute_tolerance(self, gc001, gc001_computed) -> None:  # noqa: ANN001
        actual = gc001_computed.boundaries.moon_nakshatra_end_utc
        near = actual.replace(second=0, microsecond=0)
        case = verified(
            set_field(gc001, "boundaries.moon_nakshatra_end_utc", near.isoformat())
        )
        check = next(
            c for c in evaluate_case(case, gc001_computed).checks if "moon_nakshatra_end" in c.field
        )
        assert check.dimension is Dimension.BOUNDARY
        assert check.tolerance == 120.0
        assert check.passed

    def test_boundary_time_beyond_two_minutes_fails(self, gc001, gc001_computed) -> None:  # noqa: ANN001
        actual = gc001_computed.boundaries.moon_nakshatra_end_utc
        far = datetime.fromtimestamp(actual.timestamp() + 200, tz=UTC)
        case = verified(set_field(gc001, "boundaries.moon_nakshatra_end_utc", far.isoformat()))
        check = next(
            c for c in evaluate_case(case, gc001_computed).checks if "moon_nakshatra_end" in c.field
        )
        assert not check.passed

    def test_categorical_fields_are_exact(self, gc001, gc001_computed) -> None:  # noqa: ANN001
        case = verified(set_field(gc001, "grahas.sun.rashi", "meena"))
        check = _one(evaluate_case(case, gc001_computed), "sun.rashi")
        assert check.dimension is Dimension.CATEGORICAL
        assert check.passed == (gc001_computed.grahas["sun"].rashi == "meena")


class TestUnfilledFields:
    def test_unfilled_expectations_produce_no_checks(self, gc001, gc001_computed) -> None:  # noqa: ANN001
        evaluation = evaluate_case(verified(gc001), gc001_computed)
        assert evaluation.checks == []

    def test_only_filled_fields_are_checked(self, gc001, gc001_computed) -> None:  # noqa: ANN001
        case = verified(set_field(gc001, "grahas.sun.longitude_deg", "10.0"))
        evaluation = evaluate_case(case, gc001_computed)
        assert [c.field for c in evaluation.checks] == ["grahas.sun.longitude_deg"]


class TestReport:
    def test_pending_cases_excluded_from_gate_but_reported(  # noqa: ANN001
        self, tmp_path: Path, gc001
    ) -> None:
        # deliberately wrong value: a pending case must not drag the gate down
        pending = set_field(gc001, "grahas.sun.longitude_deg", "10.0")
        save_case(pending, tmp_path / "GC-001.yaml")
        report = build_report(tmp_path)
        assert report.verified_total == 0
        assert report.pending_total >= 1
        assert report.parity is None  # nothing to gate on yet

    def test_gate_passes_when_all_verified_checks_pass(  # noqa: ANN001
        self, tmp_path: Path, gc001, gc001_computed
    ) -> None:
        case = verified(
            set_field(
                gc001,
                "grahas.sun.longitude_deg",
                f"{gc001_computed.grahas['sun'].longitude_deg:.6f}",
            )
        )
        save_case(case, tmp_path / "GC-001.yaml")
        report = build_report(tmp_path)
        assert report.verified_total == 1
        assert report.parity == 1.0
        assert report.meets_gate

    def test_gate_fails_below_threshold(  # noqa: ANN001
        self, tmp_path: Path, gc001, gc001_computed
    ) -> None:
        bad = gc001_computed.grahas["sun"].longitude_deg + 5.0
        case = verified(set_field(gc001, "grahas.sun.longitude_deg", f"{bad:.6f}"))
        save_case(case, tmp_path / "GC-001.yaml")
        report = build_report(tmp_path)
        assert report.parity == 0.0
        assert not report.meets_gate
        assert report.failures

    def test_report_renders_per_dimension_breakdown(self, tmp_path: Path, gc001) -> None:  # noqa: ANN001
        save_case(gc001, tmp_path / "GC-001.yaml")
        rendered = build_report(tmp_path).render()
        assert "PARITY REPORT" in rendered
        for dimension in Dimension:
            assert dimension.value in rendered.lower()
        assert "pending" in rendered.lower()

    def test_threshold_is_the_spec_value(self) -> None:
        assert PARITY_THRESHOLD == 0.999
