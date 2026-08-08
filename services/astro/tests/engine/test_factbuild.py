"""FactSnapshot emission: grammar, provenance, validity windows.

Runs the real engine (Moshier fallback works with no data files), asserting
everything checkable without a Jyotish reviewer.
"""

from datetime import UTC, date, datetime, time, timedelta

from sitara_schemas.facts import FACT_ID_PATTERN, FactKind, Graha

from sitara_astro.engine.factbuild import dasha_facts, natal_facts, transit_facts
from sitara_astro.engine.inputs import BirthDetails, EngineOptions, Place

BIRTH = BirthDetails(
    date=date(1990, 5, 15),
    time=time(14, 30),
    fold=None,
    place=Place(name="New Delhi, India", lat=28.6139, lon=77.2090, tz="Asia/Kolkata"),
)
OPTIONS = EngineOptions()


def test_natal_fact_ids_follow_grammar() -> None:
    facts = natal_facts(BIRTH, OPTIONS, subject="user123", chart_version=3)
    for fact in facts:
        assert FACT_ID_PATTERN.match(fact.fact_id), fact.fact_id
    ids = {f.fact_id for f in facts}
    assert "fact:natal.moon.position/natal/user123@v3" in ids
    assert "fact:natal.moon.nakshatra/natal/user123@v3" in ids
    assert "fact:natal.lagna/natal/user123@v3" in ids
    assert "fact:natal.house.cusps/natal/user123@v3" in ids
    assert "fact:natal.saturn.house/natal/user123@v3" in ids


def test_natal_validity_and_provenance() -> None:
    facts = natal_facts(BIRTH, OPTIONS, subject="user123", chart_version=1)
    birth_utc = datetime(1990, 5, 15, 9, 0, tzinfo=UTC)
    for fact in facts:
        assert fact.valid_from == birth_utc
        assert fact.valid_to is None
        assert fact.method.ayanamsa == "lahiri"
        assert fact.method.tz is not None
        assert fact.method.tz.tz == "Asia/Kolkata"
        assert fact.engine_semver
        assert fact.data_revision.startswith("swe=")


def test_transit_fact_ids_and_windows_match_spec_example_shape() -> None:
    on = date(2026, 7, 28)
    facts = transit_facts(BIRTH, OPTIONS, on, subject="user123", chart_version=3)
    ids = {f.fact_id for f in facts}
    assert "fact:transit.saturn.house/2026-07-28/user123@v3" in ids  # SPEC §5.2 verbatim
    midnight = datetime(2026, 7, 28, tzinfo=UTC)
    for fact in facts:
        if fact.kind is FactKind.TRANSIT_GRAHA_HOUSE:
            assert (fact.valid_from, fact.valid_to) == (midnight, midnight + timedelta(days=1))
        else:
            assert (fact.valid_from, fact.valid_to) == (midnight, midnight)


def test_dasha_fact_scope_is_period_start_date() -> None:
    facts = dasha_facts(BIRTH, OPTIONS, subject="user123", chart_version=1)
    for fact in facts:
        match = FACT_ID_PATTERN.match(fact.fact_id)
        assert match is not None
        assert match["scope"] == fact.valid_from.date().isoformat()
        assert match["kind_path"].startswith("dasha.vimshottari.")
        assert fact.valid_to == fact.value.end_utc  # type: ignore[union-attr]


def test_chart_version_bump_changes_every_fact_id() -> None:
    v1 = {f.fact_id for f in natal_facts(BIRTH, OPTIONS, subject="user123", chart_version=1)}
    v2 = {f.fact_id for f in natal_facts(BIRTH, OPTIONS, subject="user123", chart_version=2)}
    assert v1.isdisjoint(v2)


def test_nine_grahas_present() -> None:
    facts = natal_facts(BIRTH, OPTIONS, subject="user123", chart_version=1)
    positions = [f for f in facts if f.kind is FactKind.NATAL_GRAHA_POSITION]
    assert {f.value.graha for f in positions} == set(Graha)  # type: ignore[union-attr]
