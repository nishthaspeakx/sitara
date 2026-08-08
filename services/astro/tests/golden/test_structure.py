"""Structure tests — run for EVERY golden case regardless of verification status.

These assert what is checkable without a Jyotish reviewer: the engine runs, the
snapshots are schema-valid and internally consistent, timezone resolution matches
the IANA tzdb (`tz_expected` is ground truth — tzdb is not astrology), and output
is deterministic. Parity against human-verified values lives in test_parity.py.
"""

from datetime import UTC, datetime, timedelta

from sitara_schemas.facts import (
    RASHI_ORDER,
    DashaLevel,
    DashaPeriodValue,
    EpheSource,
    FactKind,
    Graha,
    GrahaPositionValue,
    HouseAssignmentValue,
    NakshatraValue,
)

from sitara_astro.engine.constants import DASHA_LORD_SEQUENCE, DASHA_YEARS
from sitara_astro.engine.nakshatra import nakshatra_pada
from sitara_astro.golden.case import GoldenCase

from .conftest import (
    CaseResult,
    angular_delta,
    expected_birth_utc,
    expected_utc_offset_seconds,
    run_case,
)

NATAL_FACT_COUNT = 9 + 9 + 1 + 1 + 9  # positions + nakshatras + lagna + cusps + houses


class TestEngineRuns:
    def test_expected_fact_counts(self, case: GoldenCase, result: CaseResult) -> None:
        assert len(result.natal) == NATAL_FACT_COUNT
        levels = [
            f.value.level for f in result.dasha if isinstance(f.value, DashaPeriodValue)
        ]
        assert len(levels) == len(result.dasha)
        assert levels.count(DashaLevel.MAHA) == 9
        assert levels.count(DashaLevel.ANTAR) == 81
        assert levels.count(DashaLevel.PRATYANTAR) == 729
        if case.input.transit_date_utc is not None:
            assert len(result.transit) == 18  # 9 positions + 9 house placements

    def test_fact_ids_unique(self, case: GoldenCase, result: CaseResult) -> None:
        ids = [f.fact_id for f in (*result.natal, *result.dasha, *result.transit)]
        assert len(ids) == len(set(ids))


class TestTimezoneResolution:
    """tz_expected is derived from IANA tzdb and asserted always (§5.2: tzdb is
    the sole timezone authority; no astrology vendor is trusted for tz)."""

    def test_offset_and_flags(self, case: GoldenCase, result: CaseResult) -> None:
        tz = result.natal[0].method.tz
        assert tz is not None
        assert tz.utc_offset_seconds == expected_utc_offset_seconds(case)
        assert tz.gap_shifted_minutes == case.tz_expected.gap_shifted_minutes
        assert tz.ambiguous == case.tz_expected.ambiguous
        fold = case.input.fold
        if fold is not None:
            assert tz.fold_used == fold

    def test_birth_instant_matches_tzdb(self, case: GoldenCase, result: CaseResult) -> None:
        assert result.natal[0].valid_from == expected_birth_utc(case)

    def test_all_natal_facts_share_tz_method(self, case: GoldenCase, result: CaseResult) -> None:
        first = result.natal[0].method.tz
        assert all(f.method.tz == first for f in result.natal)


class TestInternalConsistency:
    def test_positions_in_range(self, case: GoldenCase, result: CaseResult) -> None:
        for graha in Graha:
            value = result.natal_of(FactKind.NATAL_GRAHA_POSITION, graha).value
            assert isinstance(value, GrahaPositionValue)
            assert 0 <= value.longitude_deg < 360
            assert 0 <= value.degrees_in_rashi < 30
            assert RASHI_ORDER[int(value.longitude_deg // 30)] is value.rashi

    def test_ketu_opposite_rahu(self, case: GoldenCase, result: CaseResult) -> None:
        rahu = result.natal_of(FactKind.NATAL_GRAHA_POSITION, Graha.RAHU).value
        ketu = result.natal_of(FactKind.NATAL_GRAHA_POSITION, Graha.KETU).value
        assert isinstance(rahu, GrahaPositionValue) and isinstance(ketu, GrahaPositionValue)
        assert angular_delta(rahu.longitude_deg, (ketu.longitude_deg + 180.0) % 360.0) < 1e-9

    def test_nakshatra_matches_longitude(self, case: GoldenCase, result: CaseResult) -> None:
        for graha in Graha:
            pos = result.natal_of(FactKind.NATAL_GRAHA_POSITION, graha).value
            nak = result.natal_of(FactKind.NATAL_GRAHA_NAKSHATRA, graha).value
            assert isinstance(pos, GrahaPositionValue) and isinstance(nak, NakshatraValue)
            index, name, pada = nakshatra_pada(pos.longitude_deg)
            assert nak.nakshatra_index == index
            assert nak.nakshatra is name
            assert nak.pada == pada

    def test_whole_sign_houses_consistent_with_lagna(
        self, case: GoldenCase, result: CaseResult
    ) -> None:
        lagna = result.natal_of(FactKind.NATAL_LAGNA).value
        lagna_idx = RASHI_ORDER.index(lagna.rashi)  # type: ignore[union-attr]
        for graha in Graha:
            pos = result.natal_of(FactKind.NATAL_GRAHA_POSITION, graha).value
            house = result.natal_of(FactKind.NATAL_GRAHA_HOUSE, graha).value
            assert isinstance(pos, GrahaPositionValue)
            assert isinstance(house, HouseAssignmentValue)
            graha_idx = RASHI_ORDER.index(pos.rashi)
            assert house.whole_sign_house == ((graha_idx - lagna_idx) % 12) + 1


class TestDashaArithmetic:
    def test_maha_lord_is_moon_nakshatra_lord(self, case: GoldenCase, result: CaseResult) -> None:
        moon_nak = result.natal_of(FactKind.NATAL_GRAHA_NAKSHATRA, Graha.MOON).value
        assert isinstance(moon_nak, NakshatraValue)
        expected_lord = DASHA_LORD_SEQUENCE[(moon_nak.nakshatra_index - 1) % 9]
        birth = result.natal[0].valid_from
        running = self._running_period(result, DashaLevel.MAHA, birth)
        assert running.lord is expected_lord

    def test_periods_contiguous_and_span_120_years(
        self, case: GoldenCase, result: CaseResult
    ) -> None:
        mahas = self._sorted_values(result, DashaLevel.MAHA)
        for prev, nxt in zip(mahas, mahas[1:], strict=False):
            assert prev.end_utc == nxt.start_utc, "maha periods must be contiguous"
        total = mahas[-1].end_utc - mahas[0].start_utc
        assert abs(total - timedelta(days=120 * 365.25)) < timedelta(seconds=1)
        lords = [m.lord for m in mahas]
        start = DASHA_LORD_SEQUENCE.index(lords[0])
        assert lords == [DASHA_LORD_SEQUENCE[(start + i) % 9] for i in range(9)]

    def test_antars_partition_their_maha(self, case: GoldenCase, result: CaseResult) -> None:
        mahas = self._sorted_values(result, DashaLevel.MAHA)
        antars = self._sorted_values(result, DashaLevel.ANTAR)
        for maha in mahas:
            children = [a for a in antars if a.parent_lords == (maha.lord,)
                        and maha.start_utc <= a.start_utc < maha.end_utc]
            assert len(children) == 9
            assert children[0].start_utc == maha.start_utc
            assert children[-1].end_utc == maha.end_utc
            for prev, nxt in zip(children, children[1:], strict=False):
                assert prev.end_utc == nxt.start_utc
            assert children[0].lord is maha.lord  # first antar lord = maha lord
            durations = [(a.end_utc - a.start_utc).total_seconds() for a in children]
            span = (maha.end_utc - maha.start_utc).total_seconds()
            for antar, dur in zip(children, durations, strict=True):
                assert abs(dur - span * DASHA_YEARS[antar.lord] / 120.0) < 1.0

    def test_birth_falls_inside_running_periods(
        self, case: GoldenCase, result: CaseResult
    ) -> None:
        birth = result.natal[0].valid_from
        for level in DashaLevel:
            running = self._running_period(result, level, birth)
            assert running.start_utc <= birth < running.end_utc

    @staticmethod
    def _sorted_values(result: CaseResult, level: DashaLevel) -> list[DashaPeriodValue]:
        values = [
            f.value
            for f in result.dasha
            if isinstance(f.value, DashaPeriodValue) and f.value.level is level
        ]
        return sorted(values, key=lambda v: v.start_utc)

    @staticmethod
    def _running_period(
        result: CaseResult, level: DashaLevel, at: datetime
    ) -> DashaPeriodValue:
        matches = [
            v
            for v in TestDashaArithmetic._sorted_values(result, level)
            if v.start_utc <= at < v.end_utc
        ]
        assert len(matches) == 1
        return matches[0]


class TestProvenance:
    def test_method_reflects_case_options(self, case: GoldenCase, result: CaseResult) -> None:
        opts = case.input.options
        for fact in result.natal:
            assert fact.method.ayanamsa == "lahiri"
            if fact.method.node_type is not None:
                assert fact.method.node_type is opts.node_type
        cusps = result.natal_of(FactKind.NATAL_HOUSE_CUSPS)
        assert cusps.method.bhava_system is not None
        assert cusps.method.bhava_system is opts.bhava_system
        for fact in result.dasha:
            assert fact.method.dasha_year is not None
            assert fact.method.dasha_year is opts.dasha_year

    def test_data_revision_and_semver_present(self, case: GoldenCase, result: CaseResult) -> None:
        revisions = {f.data_revision for f in (*result.natal, *result.dasha, *result.transit)}
        assert len(revisions) == 1
        revision = revisions.pop()
        assert "swe=" in revision and "ephe=" in revision and "tzdata=" in revision
        assert any(src.value in revision for src in EpheSource)
        assert all(f.engine_semver for f in result.natal)

    def test_natal_facts_are_eternal(self, case: GoldenCase, result: CaseResult) -> None:
        for fact in result.natal:
            assert fact.valid_to is None

    def test_transit_validity_windows(self, case: GoldenCase, result: CaseResult) -> None:
        if case.input.transit_date_utc is None:
            assert result.transit == ()
            return
        for fact in result.transit:
            midnight = datetime.combine(
                case.input.transit_date_utc, datetime.min.time(), tzinfo=UTC
            )
            assert fact.valid_from == midnight
            if fact.kind is FactKind.TRANSIT_GRAHA_POSITION:
                assert fact.valid_to == midnight  # point-valid
            else:
                assert fact.valid_to == midnight + timedelta(days=1)  # UTC-day-valid


class TestFoldDivergence:
    def test_gc011_and_gc012_are_different_charts(self) -> None:
        """Same wall clock, different fold → different real instant. The Moon
        moves ~0.55°/hour, so the one-hour fold gap must show up in the chart —
        a regression here means `fold` is ignored after tz resolution."""
        moon_a = run_case("GC-011").natal_of(FactKind.NATAL_GRAHA_POSITION, Graha.MOON).value
        moon_b = run_case("GC-012").natal_of(FactKind.NATAL_GRAHA_POSITION, Graha.MOON).value
        assert isinstance(moon_a, GrahaPositionValue)
        assert isinstance(moon_b, GrahaPositionValue)
        delta = angular_delta(moon_a.longitude_deg, moon_b.longitude_deg)
        assert 0.3 < delta < 0.8, f"expected ~0.55° fold divergence, got {delta:.4f}°"


class TestDeterminism:
    def test_two_runs_are_byte_identical(self, case: GoldenCase) -> None:
        first = run_case(case.case_id)
        run_case.cache_clear()
        second = run_case(case.case_id)
        for a, b in zip(
            (*first.natal, *first.dasha, *first.transit),
            (*second.natal, *second.dasha, *second.transit),
            strict=True,
        ):
            assert a.model_dump_json() == b.model_dump_json()
