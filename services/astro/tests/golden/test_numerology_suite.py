"""Numerology golden suite — §5.5 wants 500 hand-computed cases at 100% parity.

Structure assertions run on every case; parity applies only to `verified` ones,
which only a named human may create. The AI never fills a numerology expectation
any more than it fills an ephemeris one.
"""

from pathlib import Path

import pytest

from sitara_astro.golden.case import CaseSource, CaseStatus
from sitara_astro.golden.numerology_case import (
    REPO_NUMEROLOGY_DIR,
    TARGET_CASE_COUNT,
    dump_case,
    load_all,
    load_case,
    missing_required,
    save_case,
    set_field,
)
from sitara_astro.golden.numerology_parity import (
    NUMEROLOGY_PARITY_THRESHOLD,
    build_report,
    evaluate_case,
)

CASES = load_all(REPO_NUMEROLOGY_DIR)


@pytest.fixture(params=CASES, ids=lambda c: c.case_id)
def case(request: pytest.FixtureRequest):  # noqa: ANN201
    return request.param


class TestSeedSet:
    def test_twenty_seed_cases_all_pending(self) -> None:
        assert len(CASES) == 20
        assert all(c.status is CaseStatus.PENDING for c in CASES)

    def test_ids_are_contiguous(self) -> None:
        assert {c.case_id for c in CASES} == {f"NC-{i:03d}" for i in range(1, 21)}

    def test_no_expected_value_is_prefilled(self) -> None:
        """Every number a reviewer must hand-compute starts empty."""
        for c in CASES:
            assert c.expected.moolank is None
            assert c.expected.bhagyank is None
            assert c.expected.chaldean_name_number is None

    def test_target_is_the_spec_number(self) -> None:
        assert TARGET_CASE_COUNT == 500

    def test_covers_the_required_categories(self) -> None:
        categories = {c.category for c in CASES}
        assert {"cross_script", "user_edited", "moolank_edge", "bhagyank_edge"} <= categories

    def test_cross_script_cases_carry_both_forms(self) -> None:
        """§22.10: the case must record what was entered AND what was confirmed."""
        for c in CASES:
            if c.category == "cross_script":
                assert c.input.script == "devanagari"
                assert c.input.confirmed_latin
                assert c.input.name_source is not None

    def test_no_case_verified_without_a_human(self) -> None:
        for c in CASES:
            if c.status is CaseStatus.VERIFIED:
                assert c.verified_by and c.source and c.verified_on


class TestStructure:
    def test_engine_computes_without_error(self, case) -> None:  # noqa: ANN001
        evaluate_case(case)  # unfilled expectations simply produce no checks

    def test_pending_case_produces_no_checks(self, case) -> None:  # noqa: ANN001
        assert evaluate_case(case) == []

    def test_missing_required_lists_what_the_reviewer_owes(self, case) -> None:  # noqa: ANN001
        missing = missing_required(case)
        assert "moolank" in missing and "bhagyank" in missing
        if case.input.confirmed_latin:
            assert "chaldean_name_number" in missing
        else:
            assert "chaldean_name_number" not in missing

    def test_round_trip_is_stable(self, case, tmp_path: Path) -> None:  # noqa: ANN001
        path = tmp_path / f"{case.case_id}.yaml"
        save_case(case, path)
        assert load_case(path) == case
        assert dump_case(load_case(path)) == dump_case(case)

    def test_native_script_is_human_readable_on_disk(self, case) -> None:  # noqa: ANN001
        """A reviewer must see लक्ष्मी, not \\u0932… escapes."""
        text = (REPO_NUMEROLOGY_DIR / f"{case.case_id}.yaml").read_text()
        assert "\\u" not in text
        if case.input.script == "devanagari":
            assert case.input.name_as_entered in text


class TestParityGate:
    def test_threshold_is_one_hundred_percent(self) -> None:
        """Numerology is arithmetic — §5.5 allows no tolerance, unlike astrology."""
        assert NUMEROLOGY_PARITY_THRESHOLD == 1.0

    def test_gate_is_dormant_until_first_sign_off(self) -> None:
        report = build_report(REPO_NUMEROLOGY_DIR)
        assert report.parity is None
        assert report.meets_gate
        assert not report.errors

    def test_report_states_progress_toward_500(self) -> None:
        rendered = build_report(REPO_NUMEROLOGY_DIR).render()
        assert "NUMEROLOGY PARITY REPORT" in rendered
        assert f"/{TARGET_CASE_COUNT} target" in rendered

    def test_a_wrong_verified_value_fails_the_gate(self, tmp_path: Path) -> None:
        # NC-001 is 1990-05-15 → moolank 6, so 7 must fail
        case = set_field(CASES[0], "moolank", "7")
        verified = case.model_copy(
            update={
                "status": CaseStatus.VERIFIED,
                "verified_by": "Test Reviewer",
                "source": CaseSource.JYOTISH_LEAD,
            }
        )
        save_case(verified, tmp_path / f"{verified.case_id}.yaml")
        report = build_report(tmp_path)
        assert report.parity == 0.0
        assert not report.meets_gate

    def test_a_single_miss_fails_even_at_ninety_nine_percent(self, tmp_path: Path) -> None:
        """100% means 100%: one bad value among many good ones still blocks."""
        good = set_field(set_field(CASES[0], "moolank", "6"), "bhagyank", "3")
        bad = set_field(CASES[1], "moolank", "9")  # 1985-11-02 → day 2 → 2
        for c in (good, bad):
            save_case(
                c.model_copy(
                    update={
                        "status": CaseStatus.VERIFIED,
                        "verified_by": "Test Reviewer",
                        "source": CaseSource.JYOTISH_LEAD,
                    }
                ),
                tmp_path / f"{c.case_id}.yaml",
            )
        report = build_report(tmp_path)
        assert 0 < report.parity < 1.0  # type: ignore[operator]
        assert not report.meets_gate
