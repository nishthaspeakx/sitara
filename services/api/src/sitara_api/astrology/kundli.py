"""Natal facts → twelve houses, for the §24.3 `KundliChart` (CC-007).

**This module computes nothing.** §5.3 binds here as everywhere: the engine
placed every graha, and the only work done below is arranging placements that
already exist into the shape a diagram draws. There is no ephemeris, no house
arithmetic and no ayanamsa in this file, and there must never be one — the
moment there is, the chart on the screen and the facts in `guidance_logs`
become two computations that can disagree.

**Every placement is selected by GRAHA IDENTITY, never by position.** This is
the M6 lesson written into a module. `moon_nakshatra_note` once took the first
nakshatra-shaped value in a payload; the engine emits one per graha with the
Sun first, so the first live run printed "The Moon sits in Purva Bhadrapada
today" citing the SUN's nakshatra — every gate green, the id in the payload,
the name matching the fact it named, and the sentence false. A kundli is the
same trap with nine chances to fall in: nine `natal.graha.house` facts arrive
in whatever order the engine emits them, and a positional read would draw a
chart that is internally consistent, plausible to a layperson, and wrong to
the one user who has had hers on paper for forty years.

So `_by_graha` builds a dict keyed by the graha the fact NAMES, and a fact
whose value does not name a graha is skipped rather than positionally assumed.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field

from sitara_schemas.facts import (
    FactKind,
    FactSnapshot,
    Graha,
    GrahaPositionValue,
    HouseAssignmentValue,
    LagnaValue,
    Rashi,
)

logger = logging.getLogger(__name__)

#: Mesha-first, as §5.2 presents rashis. The index is 1-based to match the way
#: the rest of the system counts houses and signs.
RASHI_ORDER: tuple[Rashi, ...] = tuple(Rashi)


@dataclass(frozen=True)
class KundliHouse:
    """One of twelve. `grahas` may be empty — an empty house is a fact about
    the chart, not a hole in the data, and the renderer leaves it empty rather
    than decorating it (§24.3)."""

    house: int
    rashi: Rashi
    grahas: tuple[Graha, ...] = field(default_factory=tuple)
    is_lagna: bool = False


@dataclass(frozen=True)
class Kundli:
    houses: tuple[KundliHouse, ...]
    lagna_rashi: Rashi
    #: Grahas the engine placed in no house. Always empty for a complete natal
    #: set; carried rather than dropped because a chart missing Saturn should
    #: say so instead of drawing eight grahas as though that were nine.
    unplaced: tuple[Graha, ...] = field(default_factory=tuple)


def _by_graha(
    facts: Sequence[FactSnapshot], kind: FactKind
) -> dict[Graha, HouseAssignmentValue]:
    """Index house assignments by the graha each one NAMES.

    Not `enumerate(facts)`, not `facts[i]`, not "the first one shaped like a
    house". The engine's emission order is not part of its contract, and the
    one time this system assumed it was, it published a false sentence about
    the Moon (M6, CL-009).
    """
    out: dict[Graha, HouseAssignmentValue] = {}
    for fact in facts:
        if fact.kind is not kind:
            continue
        value = fact.value
        if not isinstance(value, HouseAssignmentValue):
            # A fact of the right KIND whose value is another shape is a
            # schema change, not something to guess around.
            logger.warning("natal house fact with unexpected value shape: %s", fact.fact_id)
            continue
        if value.graha in out:
            logger.warning(
                "two house facts for %s — keeping the first, which means the "
                "engine emitted a duplicate and something upstream is wrong",
                value.graha,
            )
            continue
        out[value.graha] = value
    return out


def _lagna_of(facts: Sequence[FactSnapshot]) -> Rashi | None:
    for fact in facts:
        if fact.kind is FactKind.NATAL_LAGNA and isinstance(fact.value, LagnaValue):
            return fact.value.rashi
    return None


def build_kundli(facts: Sequence[FactSnapshot]) -> Kundli | None:
    """Arrange natal facts into twelve houses, or decline.

    Returns None when the lagna is absent, and declining is the correct
    behaviour rather than a defensive one: the whole-sign house numbering is
    counted FROM the lagna, so a chart drawn without it would need an assumed
    ascendant — and §5.4 exists precisely because a diamond drawn from a
    guessed ascendant is a confident-looking lie. Moon-chart mode is the
    caller's answer to that (it passes the Moon's rashi as the first house),
    not a default this function may take on its own.
    """
    lagna = _lagna_of(facts)
    if lagna is None:
        logger.info("no lagna fact — declining to draw a kundli (§5.4)")
        return None

    return _assemble(facts, first_house_rashi=lagna, lagna_rashi=lagna)


def build_moon_chart(facts: Sequence[FactSnapshot]) -> Kundli | None:
    """§5.4's Moon-chart mode: the Moon's rashi becomes the first house.

    Used when the birth time is unknown, so there is no ascendant to count
    from. It is a DIFFERENT chart rather than a degraded one — chandra lagna
    is a real chart in the tradition — and the caller must label it as such,
    which is why it is a separate function with a separate name instead of a
    `moon=True` flag on the one above.
    """
    # `isinstance`, not `hasattr`: the value union carries a dozen shapes and a
    # duck-typed read would happily accept any of them that grew a `graha`.
    positions: dict[Graha, GrahaPositionValue] = {}
    for fact in facts:
        if fact.kind is not FactKind.NATAL_GRAHA_POSITION:
            continue
        if isinstance(fact.value, GrahaPositionValue):
            positions.setdefault(fact.value.graha, fact.value)

    moon = positions.get(Graha.MOON)
    if moon is None:
        logger.info("no Moon position — cannot draw a Moon chart either")
        return None

    return _assemble(facts, first_house_rashi=moon.rashi, lagna_rashi=moon.rashi)


def _assemble(
    facts: Sequence[FactSnapshot], *, first_house_rashi: Rashi, lagna_rashi: Rashi
) -> Kundli:
    """Place each graha in the house the ENGINE assigned it.

    The house number comes from `HouseAssignmentValue.whole_sign_house`, which
    the engine computed. The rashi of each house is derived from the first
    house's rashi by counting forward through the zodiac — that is
    presentation (which sign sits in which box), not astrology, and it is the
    only arithmetic in this module.
    """
    assignments = _by_graha(facts, FactKind.NATAL_GRAHA_HOUSE)

    occupants: dict[int, list[Graha]] = {n: [] for n in range(1, 13)}
    unplaced: list[Graha] = []
    for graha in Graha:
        placement = assignments.get(graha)
        if placement is None:
            unplaced.append(graha)
            continue
        occupants[placement.whole_sign_house].append(graha)

    first_index = RASHI_ORDER.index(first_house_rashi)
    houses = tuple(
        KundliHouse(
            house=n,
            rashi=RASHI_ORDER[(first_index + n - 1) % 12],
            grahas=tuple(occupants[n]),
            is_lagna=(n == 1),
        )
        for n in range(1, 13)
    )
    return Kundli(houses=houses, lagna_rashi=lagna_rashi, unplaced=tuple(unplaced))


__all__ = ["RASHI_ORDER", "Kundli", "KundliHouse", "build_kundli", "build_moon_chart"]
