"""SPEC §5.2 / §34.2 — FactSnapshot contract tests (hand-written module facts.py)."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from sitara_schemas.facts import (
    FACT_ID_PATTERN,
    BhagyankValue,
    NAKSHATRA_ORDER,
    RASHI_ORDER,
    BhavaSystem,
    DashaLevel,
    DashaPeriodValue,
    DashaYearBasis,
    EpheSource,
    FactKind,
    FactMethod,
    FactPrecision,
    FactSnapshot,
    Graha,
    GrahaPositionValue,
    HouseAssignmentValue,
    HouseCuspsValue,
    LagnaValue,
    MasterNumberPolicy,
    MoolankValue,
    Nakshatra,
    NakshatraValue,
    NameNumberValue,
    NameSource,
    NodeType,
    NumerologySystem,
    Rashi,
    TzMethod,
    build_fact_id,
)

BIRTH_UTC = datetime(1990, 5, 15, 9, 0, tzinfo=UTC)

METHOD = FactMethod(
    ephe_source=EpheSource.SWISS_FILES,
    node_type=NodeType.MEAN,
    house_presentation="whole_sign",
    bhava_system=BhavaSystem.SRIPATI,
    tz=TzMethod(tz="Asia/Kolkata", utc_offset_seconds=19800),
)

ARC_SEC = FactPrecision(tolerance=1.0, unit="arc_sec")


def snapshot(kind: FactKind, fact_id: str, value: object) -> FactSnapshot:
    return FactSnapshot(
        fact_id=fact_id,
        kind=kind,
        value=value,  # type: ignore[arg-type]
        precision=ARC_SEC,
        method=METHOD,
        valid_from=BIRTH_UTC,
        valid_to=None,
        engine_semver="0.1.0",
        data_revision="swe=2.10;ephe=swiss_files;tzdata=2025.2",
    )


class TestEnums:
    def test_closed_set_sizes(self) -> None:
        assert len(Graha) == 9
        assert len(Rashi) == 12
        assert len(Nakshatra) == 27
        assert len(FactKind) == 11  # 8 astrology + 3 numerology
        assert len(DashaLevel) == 3
        assert len(NumerologySystem) == 2
        assert sum(1 for k in FactKind if k.value.startswith("numerology.")) == 3

    def test_orders_are_canonical(self) -> None:
        assert RASHI_ORDER[0] is Rashi.MESHA
        assert RASHI_ORDER[-1] is Rashi.MEENA
        assert NAKSHATRA_ORDER[0] is Nakshatra.ASHWINI
        assert NAKSHATRA_ORDER[-1] is Nakshatra.REVATI


class TestFactId:
    def test_spec_example_accepted(self) -> None:
        # verbatim example from SPEC §5.2
        assert FACT_ID_PATTERN.match("fact:transit.saturn.house/2026-07-28/user123@v3")

    def test_build_round_trips_spec_example(self) -> None:
        assert (
            build_fact_id("transit.saturn.house", "2026-07-28", "user123", 3)
            == "fact:transit.saturn.house/2026-07-28/user123@v3"
        )

    @pytest.mark.parametrize(
        "bad",
        [
            "fact:transit.saturn.house/2026-07-28/user123",  # no version
            "fact:transit/2026-07-28/user123@v3",  # kind_path needs a dot
            "transit.saturn.house/2026-07-28/user123@v3",  # missing prefix
            "fact:Transit.saturn.house/natal/user123@v1",  # uppercase kind_path
            "fact:natal.moon.nakshatra/natal/user 123@v1",  # space in subject
            "fact:natal.moon.nakshatra/natal/user123@v",  # empty version
        ],
    )
    def test_malformed_rejected(self, bad: str) -> None:
        assert FACT_ID_PATTERN.match(bad) is None

    def test_build_rejects_bad_components(self) -> None:
        with pytest.raises(ValueError):
            build_fact_id("natal", "natal", "user123", 1)


class TestValueRoundTrips:
    @pytest.mark.parametrize(
        ("kind", "fact_id", "value"),
        [
            (
                FactKind.NATAL_GRAHA_POSITION,
                "fact:natal.moon.position/natal/user123@v1",
                GrahaPositionValue(
                    graha=Graha.MOON,
                    longitude_deg=123.4567,
                    rashi=Rashi.SIMHA,
                    degrees_in_rashi=3.4567,
                    speed_deg_per_day=13.2,
                    retrograde=False,
                ),
            ),
            (
                FactKind.NATAL_GRAHA_NAKSHATRA,
                "fact:natal.moon.nakshatra/natal/user123@v1",
                NakshatraValue(
                    graha=Graha.MOON,
                    nakshatra=Nakshatra.MAGHA,
                    nakshatra_index=10,
                    pada=2,
                ),
            ),
            (
                FactKind.NATAL_LAGNA,
                "fact:natal.lagna/natal/user123@v1",
                LagnaValue(longitude_deg=201.5, rashi=Rashi.TULA),
            ),
            (
                FactKind.NATAL_HOUSE_CUSPS,
                "fact:natal.house.cusps/natal/user123@v1",
                HouseCuspsValue(
                    system=BhavaSystem.SRIPATI,
                    madhya_deg=tuple(float(i * 30) for i in range(12)),
                    sandhi_deg=tuple(float(i * 30 + 15) for i in range(12)),
                ),
            ),
            (
                FactKind.NATAL_GRAHA_HOUSE,
                "fact:natal.saturn.house/natal/user123@v1",
                HouseAssignmentValue(graha=Graha.SATURN, whole_sign_house=7, bhava=8),
            ),
            (
                FactKind.DASHA_VIMSHOTTARI_PERIOD,
                "fact:dasha.vimshottari.antar.venus/1992-01-01/user123@v1",
                DashaPeriodValue(
                    level=DashaLevel.ANTAR,
                    lord=Graha.VENUS,
                    start_utc=datetime(1992, 1, 1, tzinfo=UTC),
                    end_utc=datetime(1995, 5, 1, tzinfo=UTC),
                    parent_lords=(Graha.KETU,),
                ),
            ),
            (
                FactKind.TRANSIT_GRAHA_POSITION,
                "fact:transit.saturn.position/2026-07-28/user123@v3",
                GrahaPositionValue(
                    graha=Graha.SATURN,
                    longitude_deg=340.0,
                    rashi=Rashi.MEENA,
                    degrees_in_rashi=10.0,
                    speed_deg_per_day=-0.05,
                    retrograde=True,
                ),
            ),
            (
                FactKind.TRANSIT_GRAHA_HOUSE,
                "fact:transit.saturn.house/2026-07-28/user123@v3",
                HouseAssignmentValue(graha=Graha.SATURN, whole_sign_house=6, bhava=6),
            ),
            (
                FactKind.NUMEROLOGY_MOOLANK,
                "fact:numerology.moolank/profile/user123@v1",
                MoolankValue(value=6, birth_day=15, reduction_steps=(15, 6)),
            ),
            (
                FactKind.NUMEROLOGY_BHAGYANK,
                "fact:numerology.bhagyank/profile/user123@v1",
                BhagyankValue(
                    value=3, digits=(1, 9, 9, 0, 0, 5, 1, 5), reduction_steps=(30, 3)
                ),
            ),
            (
                FactKind.NUMEROLOGY_NAME_NUMBER,
                "fact:numerology.name_number.chaldean/profile/user123@v1",
                NameNumberValue(
                    system=NumerologySystem.CHALDEAN,
                    value=1,
                    compound_value=19,
                    latin_name="Lakshmi",
                    letter_values=(("L", 3), ("A", 1), ("K", 2), ("S", 3), ("H", 5),
                                   ("M", 4), ("I", 1)),
                    reduction_steps=(19, 10, 1),
                ),
            ),
        ],
    )
    def test_json_round_trip(self, kind: FactKind, fact_id: str, value: object) -> None:
        snap = snapshot(kind, fact_id, value)
        restored = FactSnapshot.model_validate_json(snap.model_dump_json())
        assert restored == snap
        assert restored.value.value_kind == snap.value.value_kind


class TestConsistencyValidators:
    def test_kind_value_mismatch_rejected(self) -> None:
        with pytest.raises(ValidationError, match="value_kind"):
            snapshot(
                FactKind.NATAL_LAGNA,
                "fact:natal.lagna/natal/user123@v1",
                NakshatraValue(
                    graha=Graha.MOON,
                    nakshatra=Nakshatra.MAGHA,
                    nakshatra_index=10,
                    pada=2,
                ),
            )

    def test_fact_id_domain_must_match_kind(self) -> None:
        with pytest.raises(ValidationError, match="domain"):
            snapshot(
                FactKind.TRANSIT_GRAHA_HOUSE,
                "fact:natal.saturn.house/2026-07-28/user123@v3",
                HouseAssignmentValue(graha=Graha.SATURN, whole_sign_house=6, bhava=6),
            )

    def test_malformed_fact_id_rejected(self) -> None:
        with pytest.raises(ValidationError, match="grammar"):
            snapshot(
                FactKind.NATAL_LAGNA,
                "not-a-fact-id",
                LagnaValue(longitude_deg=201.5, rashi=Rashi.TULA),
            )

    def test_naive_datetime_rejected(self) -> None:
        with pytest.raises(ValidationError):
            FactSnapshot(
                fact_id="fact:natal.lagna/natal/user123@v1",
                kind=FactKind.NATAL_LAGNA,
                value=LagnaValue(longitude_deg=201.5, rashi=Rashi.TULA),
                precision=ARC_SEC,
                method=METHOD,
                valid_from=datetime(1990, 5, 15, 9, 0),  # naive
                valid_to=None,
                engine_semver="0.1.0",
                data_revision="swe=2.10;ephe=swiss_files;tzdata=2025.2",
            )

    def test_valid_to_before_valid_from_rejected(self) -> None:
        with pytest.raises(ValidationError, match="valid_to"):
            FactSnapshot(
                fact_id="fact:natal.lagna/natal/user123@v1",
                kind=FactKind.NATAL_LAGNA,
                value=LagnaValue(longitude_deg=201.5, rashi=Rashi.TULA),
                precision=ARC_SEC,
                method=METHOD,
                valid_from=BIRTH_UTC,
                valid_to=datetime(1980, 1, 1, tzinfo=UTC),
                engine_semver="0.1.0",
                data_revision="swe=2.10;ephe=swiss_files;tzdata=2025.2",
            )

    def test_dasha_parent_depth_enforced(self) -> None:
        with pytest.raises(ValidationError, match="parent lord"):
            DashaPeriodValue(
                level=DashaLevel.PRATYANTAR,
                lord=Graha.VENUS,
                start_utc=datetime(1992, 1, 1, tzinfo=UTC),
                end_utc=datetime(1992, 6, 1, tzinfo=UTC),
                parent_lords=(Graha.KETU,),  # pratyantar needs two
            )

    def test_dasha_period_must_have_positive_span(self) -> None:
        with pytest.raises(ValidationError, match="end_utc"):
            DashaPeriodValue(
                level=DashaLevel.MAHA,
                lord=Graha.KETU,
                start_utc=datetime(1992, 1, 1, tzinfo=UTC),
                end_utc=datetime(1992, 1, 1, tzinfo=UTC),
                parent_lords=(),
            )


class TestImmutability:
    def test_snapshot_is_frozen(self) -> None:
        snap = snapshot(
            FactKind.NATAL_LAGNA,
            "fact:natal.lagna/natal/user123@v1",
            LagnaValue(longitude_deg=201.5, rashi=Rashi.TULA),
        )
        with pytest.raises(ValidationError):
            snap.engine_semver = "9.9.9"  # type: ignore[misc]

    def test_value_models_are_frozen(self) -> None:
        value = LagnaValue(longitude_deg=201.5, rashi=Rashi.TULA)
        with pytest.raises(ValidationError):
            value.longitude_deg = 0.0  # type: ignore[misc]

    def test_method_defaults(self) -> None:
        """Every domain field defaults to None: a fact states only the
        conventions it actually used, so numerology carries no ayanamsa and
        astrology carries no master-number policy."""
        method = FactMethod(ephe_source=EpheSource.MOSHIER)
        assert method.ayanamsa is None  # astrology callers set it explicitly
        assert method.node_type is None
        assert method.dasha_year is None
        assert method.numerology_system is None
        assert method.master_numbers is None
        assert DashaYearBasis.DAYS_365_25.value == "days_365_25"

    def test_numerology_method_carries_no_astrology_provenance(self) -> None:
        method = FactMethod(
            numerology_system=NumerologySystem.CHALDEAN,
            master_numbers=MasterNumberPolicy.REDUCE,
            name_source=NameSource.CONFIRMED_TRANSLITERATION,
            transliteration_scheme="iso15919",
        )
        assert method.ayanamsa is None
        assert method.ephe_source is None
        assert method.tz is None
