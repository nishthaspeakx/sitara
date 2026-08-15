"""Natal facts → twelve houses (CC-007's KundliChart, §5.3, §5.4).

**The fixture below is built to fail a positional implementation.** Its facts
are deliberately emitted in an order that does not match `Graha`'s declaration
order, and each graha's house number is distinct — so a `facts[i]` read, an
`enumerate`, or a "first house-shaped value" would place every graha in
somebody else's house and produce a chart that is internally consistent,
plausible, and wrong.

That is not a hypothetical. M6 shipped `moon_nakshatra_note` reading the first
nakshatra-shaped value in a payload the engine emits Sun-first, and the first
live run printed a false sentence about the Moon with a real fact id attached.
A kundli is the same trap with nine chances to fall into it.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sitara_schemas.facts import (
    FactKind,
    FactMethod,
    FactPrecision,
    FactSnapshot,
    Graha,
    HouseAssignmentValue,
    LagnaValue,
    Rashi,
)

from sitara_api.astrology.kundli import build_kundli, build_moon_chart

EXACT = FactPrecision(tolerance=0.0, unit="exact")
METHOD = FactMethod(house_presentation="whole_sign")
BORN = dt.datetime(1990, 5, 15, tzinfo=dt.UTC)

#: Every graha in a DIFFERENT house, so a mis-assignment cannot hide behind a
#: coincidence, and in an order that is not `Graha`'s declaration order.
HOUSE_OF: dict[Graha, int] = {
    Graha.SATURN: 2,
    Graha.MOON: 10,
    Graha.KETU: 6,
    Graha.SUN: 4,
    Graha.JUPITER: 11,
    Graha.MARS: 1,
    Graha.VENUS: 7,
    Graha.RAHU: 12,
    Graha.MERCURY: 5,
}


def _fact(kind: FactKind, fact_id: str, value: object) -> FactSnapshot:
    return FactSnapshot(
        fact_id=fact_id,
        kind=kind,
        value=value,  # type: ignore[arg-type]
        precision=EXACT,
        method=METHOD,
        valid_from=BORN,
        valid_to=None,
        engine_semver="0.1.0",
        data_revision="swisseph=2.10",
    )


def house_facts() -> list[FactSnapshot]:
    """In HOUSE_OF's order — which is not Graha's order, on purpose."""
    return [
        _fact(
            FactKind.NATAL_GRAHA_HOUSE,
            f"fact:natal.{graha.value}.house/natal/u1@v1",
            HouseAssignmentValue(graha=graha, whole_sign_house=house, bhava=house),
        )
        for graha, house in HOUSE_OF.items()
    ]


def lagna_fact(rashi: Rashi = Rashi.SIMHA) -> FactSnapshot:
    return _fact(
        FactKind.NATAL_LAGNA,
        "fact:natal.lagna/natal/u1@v1",
        LagnaValue(longitude_deg=132.5, rashi=rashi),
    )


# --- the M6 trap -----------------------------------------------------------


def test_every_graha_lands_in_the_house_the_engine_gave_it() -> None:
    """The whole point. Selected by identity, so emission order is irrelevant."""
    kundli = build_kundli([lagna_fact(), *house_facts()])

    assert kundli is not None
    placed = {
        graha: house.house for house in kundli.houses for graha in house.grahas
    }
    assert placed == HOUSE_OF


def test_shuffling_the_engines_emission_order_changes_nothing() -> None:
    """A contract test for the assumption that broke M6: the engine's order is
    not part of its contract, so the chart must not depend on it."""
    facts = [lagna_fact(), *house_facts()]
    forwards = build_kundli(facts)
    backwards = build_kundli(list(reversed(facts)))

    assert forwards is not None and backwards is not None
    assert forwards.houses == backwards.houses


def test_the_moon_is_not_in_the_suns_house() -> None:
    """Stated as its own test because it is the sentence M6 actually shipped."""
    kundli = build_kundli([lagna_fact(), *house_facts()])

    assert kundli is not None
    moon_house = next(h.house for h in kundli.houses if Graha.MOON in h.grahas)
    sun_house = next(h.house for h in kundli.houses if Graha.SUN in h.grahas)

    assert moon_house == HOUSE_OF[Graha.MOON]
    assert sun_house == HOUSE_OF[Graha.SUN]
    assert moon_house != sun_house


# --- the twelve houses -----------------------------------------------------


def test_there_are_always_twelve_houses() -> None:
    kundli = build_kundli([lagna_fact(), *house_facts()])

    assert kundli is not None
    assert [h.house for h in kundli.houses] == list(range(1, 13))


def test_the_first_house_carries_the_lagna_rashi() -> None:
    kundli = build_kundli([lagna_fact(Rashi.SIMHA), *house_facts()])

    assert kundli is not None
    assert kundli.houses[0].rashi is Rashi.SIMHA
    assert kundli.houses[0].is_lagna is True
    assert sum(h.is_lagna for h in kundli.houses) == 1


def test_rashis_run_forward_from_the_lagna_and_wrap() -> None:
    """Presentation arithmetic — which sign sits in which box — and the only
    arithmetic in the module."""
    kundli = build_kundli([lagna_fact(Rashi.MEENA), *house_facts()])

    assert kundli is not None
    assert kundli.houses[0].rashi is Rashi.MEENA
    assert kundli.houses[1].rashi is Rashi.MESHA, "wraps past the end of the zodiac"
    assert kundli.houses[11].rashi is Rashi.KUMBHA


def test_an_empty_house_is_empty_not_absent() -> None:
    """§24.3: houses that carry nothing stay empty rather than being filled
    with decoration. They still have to BE there — a kundli with nine boxes is
    not a kundli."""
    facts = [
        lagna_fact(),
        _fact(
            FactKind.NATAL_GRAHA_HOUSE,
            "fact:natal.sun.house/natal/u1@v1",
            HouseAssignmentValue(graha=Graha.SUN, whole_sign_house=4, bhava=4),
        ),
    ]

    kundli = build_kundli(facts)

    assert kundli is not None
    assert len(kundli.houses) == 12
    assert kundli.houses[3].grahas == (Graha.SUN,)
    assert all(h.grahas == () for h in kundli.houses if h.house != 4)


def test_grahas_sharing_a_house_are_all_placed() -> None:
    facts = [
        lagna_fact(),
        _fact(
            FactKind.NATAL_GRAHA_HOUSE,
            "fact:natal.sun.house/natal/u1@v1",
            HouseAssignmentValue(graha=Graha.SUN, whole_sign_house=7, bhava=7),
        ),
        _fact(
            FactKind.NATAL_GRAHA_HOUSE,
            "fact:natal.mercury.house/natal/u1@v1",
            HouseAssignmentValue(graha=Graha.MERCURY, whole_sign_house=7, bhava=7),
        ),
    ]

    kundli = build_kundli(facts)

    assert kundli is not None
    assert set(kundli.houses[6].grahas) == {Graha.SUN, Graha.MERCURY}


def test_rahu_and_ketu_are_placed_like_any_other_graha() -> None:
    """A kundli without the chhaya grahas is not a kundli (§24.3's own note)."""
    kundli = build_kundli([lagna_fact(), *house_facts()])

    assert kundli is not None
    placed = {graha for house in kundli.houses for graha in house.grahas}
    assert Graha.RAHU in placed
    assert Graha.KETU in placed


def test_a_graha_the_engine_did_not_place_is_reported_not_invented() -> None:
    """A chart missing Saturn should say so, not draw eight grahas as though
    that were nine."""
    facts = [lagna_fact(), *[f for f in house_facts() if "saturn" not in f.fact_id]]

    kundli = build_kundli(facts)

    assert kundli is not None
    assert kundli.unplaced == (Graha.SATURN,)
    assert all(Graha.SATURN not in h.grahas for h in kundli.houses)


# --- §5.4 ------------------------------------------------------------------


def test_no_lagna_means_no_diamond() -> None:
    """§5.4: whole-sign houses are counted FROM the lagna, so a chart without
    one would need a guessed ascendant — and a diamond drawn from a guess is a
    confident-looking lie. Declining is the correct answer, not a defensive
    one."""
    assert build_kundli(house_facts()) is None


def test_moon_chart_mode_is_a_different_chart_not_a_degraded_one() -> None:
    """§5.4's unknown-birth-time path. Chandra lagna is a real chart in the
    tradition, which is why it is its own function with its own name rather
    than a flag that quietly changes what `build_kundli` means."""
    from sitara_schemas.facts import GrahaPositionValue

    facts = [
        *house_facts(),
        _fact(
            FactKind.NATAL_GRAHA_POSITION,
            "fact:natal.moon.position/natal/u1@v1",
            GrahaPositionValue(
                graha=Graha.MOON,
                longitude_deg=310.0,
                rashi=Rashi.KUMBHA,
                degrees_in_rashi=10.0,
                speed_deg_per_day=13.1,
                retrograde=False,
            ),
        ),
    ]

    kundli = build_moon_chart(facts)

    assert kundli is not None
    assert kundli.houses[0].rashi is Rashi.KUMBHA
    assert kundli.lagna_rashi is Rashi.KUMBHA


def test_moon_chart_declines_without_a_moon() -> None:
    assert build_moon_chart(house_facts()) is None


# --- §5.3 ------------------------------------------------------------------


def test_this_module_computes_no_astrology() -> None:
    """§5.3: the renderer has no ephemeris, no house maths, no ayanamsa.

    Read as an import check rather than a promise in a docstring: the moment
    this module imports an engine, the chart on the screen and the facts in
    `guidance_logs` become two computations that can disagree.
    """
    import ast

    from sitara_api.astrology import kundli

    with open(kundli.__file__, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    forbidden = {"swisseph", "pyswisseph", "sitara_astro"}
    assert not (imported & forbidden), f"the renderer grew an engine: {imported & forbidden}"
    assert not any(name.startswith("sitara_api.astrology.chart_adapter") for name in imported)


@pytest.mark.parametrize("house", list(range(1, 13)))
def test_every_house_number_is_reachable(house: int) -> None:
    facts = [
        lagna_fact(),
        _fact(
            FactKind.NATAL_GRAHA_HOUSE,
            "fact:natal.sun.house/natal/u1@v1",
            HouseAssignmentValue(graha=Graha.SUN, whole_sign_house=house, bhava=house),
        ),
    ]

    kundli = build_kundli(facts)

    assert kundli is not None
    assert kundli.houses[house - 1].grahas == (Graha.SUN,)
