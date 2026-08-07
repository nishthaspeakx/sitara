"""SPEC §5.2 / §34.2 — FactSnapshot contract tests (hand-written module facts.py)."""

from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from sitara_schemas.facts import (
    FACT_ID_PATTERN,
    BhagyankValue,
    NAKSHATRA_ORDER,
    RASHI_ORDER,
    BhavaSystem,
    Choghadiya,
    DashaLevel,
    DashaPeriodValue,
    DashaYearBasis,
    DayTimingKind,
    DayTimingValue,
    EpheSource,
    FactKind,
    FactMethod,
    FactPrecision,
    FactSnapshot,
    FactSource,
    FestivalObservanceValue,
    Graha,
    GrahaPositionValue,
    HouseAssignmentValue,
    HouseCuspsValue,
    LagnaValue,
    MasterNumberPolicy,
    MoolankValue,
    MuhuratType,
    MuhuratWindowValue,
    Nakshatra,
    NakshatraBoundaryValue,
    NakshatraValue,
    NameNumberValue,
    NameSource,
    NodeType,
    NumerologySystem,
    Paksha,
    Rashi,
    SunriseSunsetValue,
    TimingQuality,
    TithiBoundaryValue,
    Tradition,
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
        assert len(FactKind) == 17  # 8 astrology + 3 numerology + 6 panchang/muhurat/festival
        assert len(DashaLevel) == 3
        assert len(NumerologySystem) == 2
        assert sum(1 for k in FactKind if k.value.startswith("numerology.")) == 3
        # M3 §5.2 Layer B/D
        assert sum(1 for k in FactKind if k.value.startswith("panchang.")) == 4
        assert len(Tradition) == 2
        assert len(Choghadiya) == 7
        assert len(FactSource) == 3

    def test_every_kind_has_a_value_kind(self) -> None:
        """A new FactKind without a KIND_VALUE_KIND row would fail open."""
        from sitara_schemas.facts import KIND_VALUE_KIND

        assert set(KIND_VALUE_KIND) == set(FactKind)

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
            # ---- M3 §5.2 Layer B/D. Subject is GLOBAL ({geohash4}-{tradition}),
            # never a user id: panchang is shared across thousands of users (§7.1).
            (
                FactKind.PANCHANG_TITHI_BOUNDARY,
                "fact:panchang.tithi.boundary/2026-08-08/te7u-amanta@v1",
                TithiBoundaryValue(
                    tithi_index=5,
                    paksha=Paksha.SHUKLA,
                    starts_utc=BIRTH_UTC,
                    ends_utc=BIRTH_UTC + timedelta(hours=23),
                ),
            ),
            (
                FactKind.PANCHANG_NAKSHATRA_BOUNDARY,
                "fact:panchang.nakshatra.boundary/2026-08-08/te7u-amanta@v1",
                NakshatraBoundaryValue(
                    nakshatra=Nakshatra.ROHINI,
                    nakshatra_index=4,
                    starts_utc=BIRTH_UTC,
                    ends_utc=BIRTH_UTC + timedelta(hours=25),
                ),
            ),
            (
                FactKind.PANCHANG_SUNRISE_SUNSET,
                "fact:panchang.sunrise_sunset/2026-08-08/te7u-amanta@v1",
                SunriseSunsetValue(
                    sunrise_utc=BIRTH_UTC,
                    solar_noon_utc=BIRTH_UTC + timedelta(hours=6),
                    sunset_utc=BIRTH_UTC + timedelta(hours=12),
                    next_sunrise_utc=BIRTH_UTC + timedelta(hours=24),
                ),
            ),
            (
                FactKind.PANCHANG_DAY_TIMING,
                "fact:panchang.day_timing.rahu_kaal/2026-08-08/te7u-amanta@v1",
                DayTimingValue(
                    timing=DayTimingKind.RAHU_KAAL,
                    quality=TimingQuality.INAUSPICIOUS,
                    starts_utc=BIRTH_UTC,
                    ends_utc=BIRTH_UTC + timedelta(minutes=90),
                ),
            ),
            (
                FactKind.MUHURAT_WINDOW,
                "fact:muhurat.window.marriage/2026-08-08/tsz4-amanta@v1",
                MuhuratWindowValue(
                    muhurat_type=MuhuratType.MARRIAGE,
                    quality=TimingQuality.AUSPICIOUS,
                    place_label="Jaipur",
                    place_tz="Asia/Kolkata",
                    starts_utc=BIRTH_UTC,
                    ends_utc=BIRTH_UTC + timedelta(hours=2),
                ),
            ),
            (
                FactKind.FESTIVAL_OBSERVANCE,
                "fact:festival.observance/2026-08-08/te7u-amanta@v1",
                FestivalObservanceValue(
                    festival_id="raksha_bandhan",
                    date_local=date(2026, 8, 28),
                    region="in-north",
                    tradition=Tradition.PURNIMANTA,
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


class TestM3PanchangValues:
    """§5.2 Layer B/D — the panchang/muhurat/festival fact contract."""

    def test_paksha_must_agree_with_tithi_index(self) -> None:
        """Paksha is arithmetic, not a vendor's opinion: 1-15 shukla, 16-30 krishna."""
        with pytest.raises(ValidationError, match="krishna"):
            TithiBoundaryValue(
                tithi_index=20,
                paksha=Paksha.SHUKLA,
                starts_utc=BIRTH_UTC,
                ends_utc=BIRTH_UTC + timedelta(hours=20),
            )

    def test_nakshatra_index_must_match_name(self) -> None:
        with pytest.raises(ValidationError, match="nakshatra_index"):
            NakshatraBoundaryValue(
                nakshatra=Nakshatra.ROHINI,
                nakshatra_index=7,
                starts_utc=BIRTH_UTC,
                ends_utc=BIRTH_UTC + timedelta(hours=20),
            )

    @pytest.mark.parametrize("delta_hours", [0, -1])
    def test_window_must_move_forward(self, delta_hours: int) -> None:
        with pytest.raises(ValidationError, match="ends_utc"):
            DayTimingValue(
                timing=DayTimingKind.RAHU_KAAL,
                quality=TimingQuality.INAUSPICIOUS,
                starts_utc=BIRTH_UTC,
                ends_utc=BIRTH_UTC + timedelta(hours=delta_hours),
            )

    def test_sunrise_ordering_enforced(self) -> None:
        with pytest.raises(ValidationError, match="solar_noon"):
            SunriseSunsetValue(
                sunrise_utc=BIRTH_UTC,
                solar_noon_utc=BIRTH_UTC + timedelta(hours=13),  # after sunset
                sunset_utc=BIRTH_UTC + timedelta(hours=12),
                next_sunrise_utc=BIRTH_UTC + timedelta(hours=24),
            )

    def test_choghadiya_requires_name_and_part(self) -> None:
        with pytest.raises(ValidationError, match="choghadiya"):
            DayTimingValue(
                timing=DayTimingKind.CHOGHADIYA_DAY,
                quality=TimingQuality.AUSPICIOUS,
                starts_utc=BIRTH_UTC,
                ends_utc=BIRTH_UTC + timedelta(minutes=90),
            )

    def test_non_choghadiya_must_not_carry_a_name(self) -> None:
        with pytest.raises(ValidationError, match="choghadiya"):
            DayTimingValue(
                timing=DayTimingKind.RAHU_KAAL,
                quality=TimingQuality.INAUSPICIOUS,
                choghadiya=Choghadiya.AMRIT,
                part_index=2,
                starts_utc=BIRTH_UTC,
                ends_utc=BIRTH_UTC + timedelta(minutes=90),
            )

    def test_muhurat_carries_the_place_it_was_computed_for(self) -> None:
        """§30.2: a window for 'wedding in Jaipur' is labelled with Jaipur and
        computed in Jaipur's timezone — it can never render as the user's city."""
        value = MuhuratWindowValue(
            muhurat_type=MuhuratType.MARRIAGE,
            quality=TimingQuality.AUSPICIOUS,
            place_label="Jaipur",
            place_tz="Asia/Kolkata",
            starts_utc=BIRTH_UTC,
            ends_utc=BIRTH_UTC + timedelta(hours=2),
        )
        assert value.place_label == "Jaipur"
        assert value.place_tz == "Asia/Kolkata"

    def test_festival_id_is_a_slug_not_rendered_copy(self) -> None:
        """A vendor's English festival name must never reach a user (§2.4)."""
        with pytest.raises(ValidationError):
            FestivalObservanceValue(
                festival_id="Raksha Bandhan",
                date_local=date(2026, 8, 28),
                region="in-north",
                tradition=Tradition.PURNIMANTA,
            )


class TestSnapshotProvenance:
    """§5.2 — a snapshot is (id, value, source, confidence)."""

    def test_source_defaults_to_layer_a(self) -> None:
        snap = snapshot(
            FactKind.NATAL_LAGNA,
            "fact:natal.lagna/natal/user123@v1",
            LagnaValue(longitude_deg=201.5, rashi=Rashi.TULA),
        )
        assert snap.source is FactSource.LAYER_A
        assert snap.confidence is None

    def test_pre_m3_artefact_still_validates(self) -> None:
        """M2 wrote snapshots without source/confidence; old Trust Sheets must
        keep reading (§34.2 — artefacts are read as written, never recomputed)."""
        legacy = {
            "fact_id": "fact:natal.lagna/natal/user123@v1",
            "kind": FactKind.NATAL_LAGNA.value,
            "value": {"value_kind": "lagna", "longitude_deg": 201.5, "rashi": "tula"},
            "precision": {"tolerance": 1.0, "unit": "arc_sec"},
            "method": {"ephe_source": "swiss_files"},
            "valid_from": BIRTH_UTC.isoformat(),
            "valid_to": None,
            "engine_semver": "0.1.0",
            "data_revision": "swe=2.10;ephe=swiss_files;tzdata=2025.2",
        }
        restored = FactSnapshot.model_validate(legacy)
        assert restored.source is FactSource.LAYER_A
