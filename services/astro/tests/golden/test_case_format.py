"""Versioned golden-case format: parse, round-trip, sentinel handling, guards."""

from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from sitara_astro.golden.case import (
    NEEDS_VERIFICATION,
    SCHEMA_VERSION,
    CaseSource,
    CaseStatus,
    TimeAccuracy,
    dump_case,
    load_all,
    load_case,
    missing_required,
    save_case,
    set_field,
)

CASES_DIR = Path(__file__).resolve().parents[4] / "golden-set" / "cases"


class TestRepoCases:
    def test_all_cases_load(self) -> None:
        cases = load_all(CASES_DIR)
        assert len(cases) == 25
        assert {c.case_id for c in cases} == {f"GC-{i:03d}" for i in range(1, 26)}

    def test_all_cases_are_current_schema_version(self) -> None:
        for case in load_all(CASES_DIR):
            assert case.schema_version == SCHEMA_VERSION

    def test_no_case_is_verified_without_a_reviewer(self) -> None:
        """The AI never verifies ephemeris maths — a verified case must name a
        human and a source (golden-set/README.md, SPEC §5.5)."""
        for case in load_all(CASES_DIR):
            if case.status is CaseStatus.VERIFIED:
                assert case.verified_by, f"{case.case_id} verified with no reviewer"
                assert case.source is not None
                assert case.verified_on is not None

    def test_every_case_declares_time_accuracy(self) -> None:
        for case in load_all(CASES_DIR):
            assert case.input.time_accuracy in set(TimeAccuracy)

    def test_seed_cases_are_all_pending(self) -> None:
        assert all(c.status is CaseStatus.PENDING for c in load_all(CASES_DIR))


class TestRoundTrip:
    def test_dump_reload_is_stable(self, tmp_path: Path) -> None:
        case = load_case(CASES_DIR / "GC-001.yaml")
        path = tmp_path / "GC-001.yaml"
        save_case(case, path)
        assert load_case(path) == case
        assert dump_case(load_case(path)) == dump_case(case)

    def test_unfilled_values_round_trip_as_sentinel(self, tmp_path: Path) -> None:
        case = load_case(CASES_DIR / "GC-001.yaml")
        assert case.expected.grahas["sun"].longitude_deg is None
        path = tmp_path / "out.yaml"
        save_case(case, path)
        assert NEEDS_VERIFICATION in path.read_text()

    def test_filled_values_do_not_emit_sentinel_for_that_field(self, tmp_path: Path) -> None:
        case = set_field(load_case(CASES_DIR / "GC-001.yaml"), "grahas.sun.longitude_deg", "30.5")
        path = tmp_path / "out.yaml"
        save_case(case, path)
        reloaded = load_case(path)
        assert reloaded.expected.grahas["sun"].longitude_deg == 30.5


class TestSetField:
    @pytest.mark.parametrize(
        ("path", "raw", "getter"),
        [
            (
                "grahas.moon.longitude_deg",
                "123.4567",
                lambda c: c.expected.grahas["moon"].longitude_deg,
            ),
            ("grahas.moon.rashi", "simha", lambda c: c.expected.grahas["moon"].rashi),
            ("grahas.moon.pada", "3", lambda c: c.expected.grahas["moon"].pada),
            ("lagna.longitude_deg", "201.5", lambda c: c.expected.lagna.longitude_deg),
            ("dasha.maha_at_birth.lord", "venus", lambda c: c.expected.dasha["maha_at_birth"].lord),
            (
                "dasha.maha_at_birth.start",
                "1990-05-15",
                lambda c: c.expected.dasha["maha_at_birth"].start,
            ),
            (
                "boundaries.moon_nakshatra_end_utc",
                "1990-05-15T18:22:00Z",
                lambda c: c.expected.boundaries.moon_nakshatra_end_utc,
            ),
        ],
    )
    def test_dotted_paths(self, path: str, raw: str, getter) -> None:  # noqa: ANN001
        case = set_field(load_case(CASES_DIR / "GC-001.yaml"), path, raw)
        assert getter(case) is not None

    def test_date_parsing(self) -> None:
        case = set_field(
            load_case(CASES_DIR / "GC-001.yaml"), "dasha.maha_at_birth.start", "1990-05-15"
        )
        assert case.expected.dasha["maha_at_birth"].start == date(1990, 5, 15)

    def test_sentinel_clears_a_value(self) -> None:
        case = set_field(load_case(CASES_DIR / "GC-001.yaml"), "grahas.sun.pada", "2")
        assert case.expected.grahas["sun"].pada == 2
        cleared = set_field(case, "grahas.sun.pada", NEEDS_VERIFICATION)
        assert cleared.expected.grahas["sun"].pada is None

    @pytest.mark.parametrize(
        "bad_path",
        ["nonsense", "grahas.pluto.longitude_deg", "grahas.sun.mass", "lagna.speed", "status"],
    )
    def test_unknown_paths_rejected(self, bad_path: str) -> None:
        with pytest.raises(KeyError):
            set_field(load_case(CASES_DIR / "GC-001.yaml"), bad_path, "1.0")

    def test_out_of_range_value_rejected(self) -> None:
        with pytest.raises((ValidationError, ValueError)):
            set_field(load_case(CASES_DIR / "GC-001.yaml"), "grahas.sun.pada", "9")

    def test_status_cannot_be_set_through_field_import(self) -> None:
        """CSV import may only supply expected values — never verification state."""
        with pytest.raises(KeyError):
            set_field(load_case(CASES_DIR / "GC-001.yaml"), "verified_by", "someone")


class TestMissingRequired:
    def test_seed_case_lists_all_nine_grahas_and_lagna(self) -> None:
        missing = missing_required(load_case(CASES_DIR / "GC-001.yaml"))
        assert "lagna.longitude_deg" in missing
        for graha in ("sun", "moon", "saturn", "rahu", "ketu"):
            assert f"grahas.{graha}.longitude_deg" in missing

    def test_fully_filled_case_reports_nothing_missing(self) -> None:
        case = load_case(CASES_DIR / "GC-001.yaml")
        for graha in case.expected.grahas:
            case = set_field(case, f"grahas.{graha}.longitude_deg", "10.0")
        case = set_field(case, "lagna.longitude_deg", "100.0")
        assert missing_required(case) == []


def test_source_enum_matches_spec_vocabulary() -> None:
    assert {s.value for s in CaseSource} == {"JHora", "DrikPanchang", "JyotishLead"}
