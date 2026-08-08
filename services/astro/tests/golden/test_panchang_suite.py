"""Panchang golden suite (PC-*) — SPEC §5.2 Layer C, §5.5.

The property that matters most here is that the gate is *dormant but wired*:
every value is currently the NEEDS_VERIFICATION sentinel, so nothing gates —
but the moment the Jyotish lead signs off one case, the gate must arm by
itself. `test_gate_arms_on_first_sign_off` proves exactly that, and
`test_a_wrong_verified_value_fails_the_gate` proves it can still say no.
"""

import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sitara_schemas.facts import (
    FactKind,
    NakshatraBoundaryValue,
    TithiBoundaryValue,
    Tradition,
)

from sitara_astro.engine.daytimings import day_timings
from sitara_astro.engine.inputs import EngineOptions, Place
from sitara_astro.engine.panchang_factbuild import panchang_facts
from sitara_astro.engine.riseset import sun_day
from sitara_astro.golden.case import NEEDS_VERIFICATION, CaseSource, CaseStatus
from sitara_astro.golden.panchang_case import (
    LEAF_FIELDS,
    REPO_PANCHANG_DIR,
    REQUIRED_FIELDS,
    TARGET_CASE_COUNT,
    PanchangCase,
    dump_case,
    load_all,
    load_case,
    missing_required,
    parse_local,
    save_case,
    set_field,
)
from sitara_astro.golden.panchang_parity import (
    PANCHANG_PARITY_THRESHOLD,
    build_report,
    evaluate_case,
)

CASES = load_all(REPO_PANCHANG_DIR)


@pytest.fixture(params=CASES, ids=lambda c: c.case_id)
def case(request: pytest.FixtureRequest) -> PanchangCase:
    return request.param


def local_string(moment: dt.datetime, tz: str) -> str:
    return moment.astimezone(ZoneInfo(tz)).strftime("%Y-%m-%d %H:%M:%S")


def fill_from_engine(case: PanchangCase) -> PanchangCase:
    """Fill a case with what OUR engine says.

    This is a test fixture, never a verification path: it proves the harness
    wiring end to end. A real expectation comes from Drik Panchang / JHora and
    only a named human may mark it verified (§5.5).
    """
    place = Place(name=case.input.place, lat=case.input.lat, lon=case.input.lon, tz=case.input.tz)
    tz = case.input.tz
    day = sun_day(case.input.local_date, place)
    facts = {
        f.kind: f.value
        for f in panchang_facts(
            case.input.local_date, place, case.input.tradition, EngineOptions(),
            include_day_timings=False,
        )
    }
    tithi = facts[FactKind.PANCHANG_TITHI_BOUNDARY]
    nakshatra = facts[FactKind.PANCHANG_NAKSHATRA_BOUNDARY]
    # FactValue is a discriminated union; narrow it rather than suppressing —
    # a kind/value mismatch here would be a real contract bug (§34.2).
    assert isinstance(tithi, TithiBoundaryValue)
    assert isinstance(nakshatra, NakshatraBoundaryValue)
    timings = day_timings(case.input.local_date, place)
    rahu = next(t for t in timings if t.timing.value == "rahu_kaal")

    values = {
        "sun.sunrise_local": local_string(day.sunrise, tz),
        "sun.sunset_local": local_string(day.sunset, tz),
        "tithi.index_at_sunrise": str(tithi.tithi_index),
        "tithi.paksha": tithi.paksha.value,
        "tithi.ends_local": local_string(tithi.ends_utc, tz),
        "nakshatra.name_at_sunrise": nakshatra.nakshatra.value,
        "nakshatra.ends_local": local_string(nakshatra.ends_utc, tz),
        "day_timings.rahu_kaal.starts_local": local_string(rahu.starts_utc, tz),
        "day_timings.rahu_kaal.ends_local": local_string(rahu.ends_utc, tz),
    }
    filled = case
    for field, value in values.items():
        filled = set_field(filled, field, value)
    return filled


def signed_off(case: PanchangCase) -> PanchangCase:
    return case.model_copy(
        update={
            "status": CaseStatus.VERIFIED,
            "verified_by": "Jyotish lead (test)",
            "verified_on": dt.date(2026, 8, 7),
            "source": CaseSource.DRIK_PANCHANG,
        }
    )


class TestSeedSet:
    def test_eight_seed_cases_all_pending(self) -> None:
        assert len(CASES) == 8
        assert all(c.status is CaseStatus.PENDING for c in CASES)

    def test_ids_are_contiguous(self) -> None:
        assert [c.case_id for c in CASES] == [f"PC-{i:03d}" for i in range(1, 9)]

    def test_no_expected_value_is_prefilled(self) -> None:
        """An AI never supplies an expected value — that is the exact failure
        §5 exists to prevent."""
        for case in CASES:
            for field in LEAF_FIELDS:
                cursor = case.expected
                for part in field.split("."):
                    cursor = getattr(cursor, part)
                assert cursor is None, f"{case.case_id}.{field} is prefilled"

    def test_no_case_verified_without_a_human(self) -> None:
        for case in CASES:
            if case.status is CaseStatus.VERIFIED:
                assert case.verified_by and case.source

    def test_covers_the_edge_categories_layer_c_names(self) -> None:
        """§5.2 Layer C: 'DST transitions, midnight births, leap years,
        southern-hemisphere, historical timezones, regional calendar splits'."""
        categories = {c.category for c in CASES}
        assert {"southern_hemisphere", "dst_transition", "amanta_purnimanta_split"} <= categories

    def test_both_traditions_are_represented(self) -> None:
        traditions = {c.input.tradition for c in CASES}
        assert traditions == {Tradition.AMANTA, Tradition.PURNIMANTA}

    def test_target_is_stated(self) -> None:
        assert TARGET_CASE_COUNT >= len(CASES)


class TestStructure:
    def test_engine_computes_without_error(self, case: PanchangCase) -> None:
        assert evaluate_case(case) is not None

    def test_pending_case_produces_no_checks(self, case: PanchangCase) -> None:
        """Unfilled is not failed: the sentinel means 'not done yet'."""
        assert evaluate_case(case) == []

    def test_missing_required_lists_what_the_reviewer_owes(self, case: PanchangCase) -> None:
        assert set(missing_required(case)) == set(REQUIRED_FIELDS)

    def test_round_trip_is_stable(self, case: PanchangCase, tmp_path: Path) -> None:
        path = tmp_path / f"{case.case_id}.yaml"
        save_case(case, path)
        assert load_case(path) == case
        assert dump_case(load_case(path)) == dump_case(case)

    def test_sentinel_survives_a_round_trip(self, case: PanchangCase, tmp_path: Path) -> None:
        path = tmp_path / f"{case.case_id}.yaml"
        save_case(case, path)
        assert NEEDS_VERIFICATION in path.read_text()


class TestLocalTimeParsing:
    def test_bare_time_uses_the_case_date(self) -> None:
        case = CASES[0]
        parsed = parse_local("06:17:29", case)
        assert parsed.date() == case.input.local_date
        assert parsed.tzinfo is not None

    def test_full_datetime_carries_its_own_date(self) -> None:
        """Tithi and nakshatra edges cross midnight freely, so the reviewer
        must be able to write the date they read."""
        case = CASES[0]
        parsed = parse_local("2026-08-07 21:04:00", case)
        assert parsed.date() == dt.date(2026, 8, 7)

    def test_unreadable_time_is_rejected_loudly(self) -> None:
        with pytest.raises(ValueError, match="cannot read local time"):
            parse_local("sometime tuesday", CASES[0])


class TestParityGate:
    def test_threshold_matches_the_spec(self) -> None:
        assert PANCHANG_PARITY_THRESHOLD == 0.999

    def test_gate_is_dormant_until_first_sign_off(self) -> None:
        report = build_report(REPO_PANCHANG_DIR)
        assert report.parity is None
        assert report.meets_gate is True
        assert "gate arms on the reviewer's first sign-off" in report.render()

    def test_gate_arms_on_first_sign_off(self, tmp_path: Path) -> None:
        """The founder's requirement: verifying PC-001 must arm the gate with
        no further wiring. Values here come from our own engine — a real
        sign-off uses Drik Panchang — but the wiring under test is identical."""
        case = signed_off(fill_from_engine(CASES[0]))
        save_case(case, tmp_path / f"{case.case_id}.yaml")

        report = build_report(tmp_path)
        assert len(report.verified) == 1
        assert report.checks_total >= 9, "a signed-off case must produce real checks"
        assert report.parity == 1.0
        assert report.meets_gate is True
        assert "PARITY: 100.0000%" in report.render()

    def test_a_wrong_verified_value_fails_the_gate(self, tmp_path: Path) -> None:
        """Armed means it can say no. Ten minutes is five times the §5.5
        boundary tolerance."""
        filled = fill_from_engine(CASES[0])
        assert filled.expected.sun.sunrise_local is not None
        wrong = parse_local(filled.expected.sun.sunrise_local, filled) + dt.timedelta(minutes=10)
        case = signed_off(
            set_field(filled, "sun.sunrise_local", wrong.strftime("%Y-%m-%d %H:%M:%S"))
        )
        save_case(case, tmp_path / f"{case.case_id}.yaml")

        report = build_report(tmp_path)
        assert report.meets_gate is False
        assert report.failures
        assert "sun.sunrise_local" in report.render()

    def test_a_two_minute_miss_is_within_tolerance(self, tmp_path: Path) -> None:
        """§5.5 states ≤2 min for boundary times — that is a real tolerance,
        not a rounding accident."""
        filled = fill_from_engine(CASES[0])
        assert filled.expected.tithi.ends_local is not None
        near = parse_local(filled.expected.tithi.ends_local, filled) + dt.timedelta(seconds=110)
        case = signed_off(
            set_field(filled, "tithi.ends_local", near.strftime("%Y-%m-%d %H:%M:%S"))
        )
        save_case(case, tmp_path / f"{case.case_id}.yaml")
        assert build_report(tmp_path).meets_gate is True

    def test_pending_cases_never_gate_alongside_a_verified_one(self, tmp_path: Path) -> None:
        """Authoring more cases must never destabilise a green build."""
        verified = signed_off(fill_from_engine(CASES[0]))
        save_case(verified, tmp_path / f"{verified.case_id}.yaml")
        for pending in CASES[1:4]:
            save_case(pending, tmp_path / f"{pending.case_id}.yaml")

        report = build_report(tmp_path)
        assert len(report.verified) == 1
        assert len(report.pending) == 3
        assert report.meets_gate is True

    def test_an_engine_error_fails_the_gate_rather_than_passing_silently(
        self, tmp_path: Path
    ) -> None:
        """A case the engine cannot compute must never count as agreement."""
        broken = signed_off(fill_from_engine(CASES[0])).model_copy(
            update={
                "input": CASES[0].input.model_copy(update={"tz": "Mars/Olympus"}),
            }
        )
        save_case(broken, tmp_path / f"{broken.case_id}.yaml")
        report = build_report(tmp_path)
        assert report.errors
        assert report.meets_gate is False


class TestTzProvenance:
    def test_offset_is_asserted_when_filled(self, tmp_path: Path) -> None:
        """§5.2: timezone comes from the IANA tzdb, never from a vendor — so
        the suite checks it independently of any astrology value."""
        case = CASES[0]
        filled = fill_from_engine(case)
        filled.tz_expected.utc_offset = "+05:30"
        checks = evaluate_case(filled)
        tz_checks = [c for c in checks if c.field == "tz.utc_offset"]
        assert len(tz_checks) == 1
        assert tz_checks[0].passed is True

    def test_a_wrong_offset_is_caught(self) -> None:
        filled = fill_from_engine(CASES[0])
        filled.tz_expected.utc_offset = "+00:00"
        tz_checks = [c for c in evaluate_case(filled) if c.field == "tz.utc_offset"]
        assert tz_checks[0].passed is False
