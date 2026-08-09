"""The ranking engine (§6.3's "daily-guidance (ranking engine, 17 modules)").

Two rules govern every line here, and they pull in opposite directions, which
is why they are both stated as code rather than as intent.

**§34.3: "the ranking engine emits module IDs from this enum and nothing
else."** The enum is `sitara_schemas.modules.MorningModule`, seventeen members,
closed. This module never constructs a module id from a string, and the
selection functions return enum members so that a typo is an AttributeError at
import rather than a card that renders as a blank on someone's Today screen.

**§5.3: cite-or-die.** A module that has no fact to stand on is not emitted.
That is the rule the whole ranking has to bend around: the engine cannot pick
"favourable window" because the day would read better with one, only because a
`muhurat.window` or `panchang.day_timing` fact is in hand. A ranking engine
that emitted a module and left the composer to find something to say would move
the fabrication one file downstream — and §7.1's degrade path exists precisely
so that "fewer modules" is always an available answer.

**§28.2: "Density changes ranking-engine output count, never facts."** The
density modes therefore take effect as CAPS applied after selection, never as a
different fact set or a different threshold. LOW and HIGH looking at the same
morning see the same facts and a different number of cards.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sitara_schemas.facts import FactKind, FactSnapshot
from sitara_schemas.modules import MORNING_MODULE_ORDER, MorningModule

from sitara_api.daily_guidance.types import Density

# ---------------------------------------------------------------------------
# §28.2's anatomy, mapped onto §34.3's seventeen
# ---------------------------------------------------------------------------

#: §28.2 items (2)–(4): Tara's line, the core guidance card, and the practical
#: strip of "colour · number · one favourable window · one caution window".
#: Present at every density — LOW is defined as exactly this and nothing else.
BASE_MODULES: tuple[MorningModule, ...] = (
    MorningModule.ENERGY_OF_DAY,
    MorningModule.PERSONAL_CHART_THEME,
    MorningModule.COLOUR,
    MorningModule.NUMBER,
    MorningModule.FAVOURABLE_WINDOW,
    MorningModule.CAUTION_WINDOW,
)

#: §28.2 item (6), "panchang summary row". LOW collapses it; MED and HIGH
#: carry it.
PANCHANG_ROW: tuple[MorningModule, ...] = (MorningModule.MOON_NAKSHATRA_NOTE,)

#: §28.2 item (5): "contextual cards ranked by the engine (max 4 visible)" —
#: family reminder, priority nudge, festival, food, work, relationship, goal
#: check. `what_to_avoid` joins them: it is one of the seventeen, it is not part
#: of the practical strip, and a module of the enum with nowhere to be emitted
#: would be a module that can never appear.
CONTEXTUAL_POOL: tuple[MorningModule, ...] = (
    MorningModule.FAMILY_REMINDER,
    MorningModule.PRIORITIES,
    MorningModule.FESTIVAL_OBSERVANCE,
    MorningModule.WHAT_TO_AVOID,
    MorningModule.FOOD_AND_DRINK,
    MorningModule.WORK,
    MorningModule.RELATIONSHIP,
    MorningModule.GOAL_CHECK,
)

#: §28.2's HIGH mode: "+ full timings inline (choghadiya strip), dasha context
#: line, extra observance cards".
HIGH_EXTRAS: tuple[MorningModule, ...] = (
    MorningModule.SPIRITUAL_PRACTICE,
    MorningModule.TOMORROW_PREP_TEASER,
)

#: §28.2's "max 4 visible" is the ceiling; the density mode sets the actual
#: count. LOW is "practical strip only", MED is "+ 2 contextual cards".
CONTEXTUAL_CAP: dict[Density, int] = {
    Density.LOW: 0,
    Density.MED: 2,
    Density.HIGH: 4,
}

#: A safety net, not a policy: every module of the seventeen must appear in
#: exactly one bucket above, or the engine can never emit it. Asserted at import
#: because a mis-bucketed module is invisible in every other way.
_BUCKETED = BASE_MODULES + PANCHANG_ROW + CONTEXTUAL_POOL + HIGH_EXTRAS
assert set(_BUCKETED) == set(MORNING_MODULE_ORDER), (
    "every §34.3 module must be reachable from exactly one density bucket; "
    f"unreachable: {sorted(set(MORNING_MODULE_ORDER) - set(_BUCKETED))}"
)
assert len(_BUCKETED) == len(set(_BUCKETED)) == 17, "the §34.3 enum is closed at 17"


# ---------------------------------------------------------------------------
# What each module needs before it may be emitted (§5.3)
# ---------------------------------------------------------------------------

#: The fact kinds a module can be built from. A module is emittable when AT
#: LEAST ONE of its kinds is present — "at least one" rather than "all" because
#: several modules have more than one honest source (a favourable window can
#: come from a muhurat or from a choghadiya part), and requiring both would
#: silently drop the module whenever only the better source was available.
#:
#: `PRIORITIES` and `GOAL_CHECK` are the two that carry an empty requirement,
#: and they are the exception that proves the rule: neither makes an
#: astrological claim. A priority nudge repeats what the user told us at
#: onboarding (S11) and a goal check repeats a `goals` row. They are still
#: gated — by `available_inputs` below, on the user's own data — but a fact-ID
#: is the wrong gate for a sentence that asserts nothing about the sky.
MODULE_FACT_KINDS: dict[MorningModule, tuple[FactKind, ...]] = {
    MorningModule.ENERGY_OF_DAY: (
        FactKind.PANCHANG_TITHI_BOUNDARY,
        FactKind.TRANSIT_GRAHA_POSITION,
    ),
    MorningModule.PERSONAL_CHART_THEME: (
        FactKind.TRANSIT_GRAHA_HOUSE,
        FactKind.DASHA_VIMSHOTTARI_PERIOD,
        FactKind.NATAL_GRAHA_HOUSE,
    ),
    MorningModule.MOON_NAKSHATRA_NOTE: (
        FactKind.PANCHANG_NAKSHATRA_BOUNDARY,
        FactKind.NATAL_GRAHA_NAKSHATRA,
    ),
    MorningModule.COLOUR: (FactKind.PANCHANG_TITHI_BOUNDARY,),
    MorningModule.NUMBER: (
        FactKind.NUMEROLOGY_MOOLANK,
        FactKind.NUMEROLOGY_BHAGYANK,
    ),
    MorningModule.FAVOURABLE_WINDOW: (
        FactKind.MUHURAT_WINDOW,
        FactKind.PANCHANG_DAY_TIMING,
    ),
    MorningModule.CAUTION_WINDOW: (FactKind.PANCHANG_DAY_TIMING,),
    MorningModule.PRIORITIES: (),
    MorningModule.WHAT_TO_AVOID: (FactKind.PANCHANG_DAY_TIMING,),
    MorningModule.FOOD_AND_DRINK: (FactKind.PANCHANG_TITHI_BOUNDARY,),
    MorningModule.WORK: (FactKind.TRANSIT_GRAHA_HOUSE,),
    MorningModule.RELATIONSHIP: (FactKind.TRANSIT_GRAHA_HOUSE,),
    MorningModule.FAMILY_REMINDER: (),
    MorningModule.FESTIVAL_OBSERVANCE: (FactKind.FESTIVAL_OBSERVANCE,),
    MorningModule.GOAL_CHECK: (),
    MorningModule.SPIRITUAL_PRACTICE: (
        FactKind.FESTIVAL_OBSERVANCE,
        FactKind.PANCHANG_TITHI_BOUNDARY,
    ),
    MorningModule.TOMORROW_PREP_TEASER: (
        FactKind.PANCHANG_TITHI_BOUNDARY,
        FactKind.TRANSIT_GRAHA_POSITION,
    ),
}

assert set(MODULE_FACT_KINDS) == set(MORNING_MODULE_ORDER), (
    "every §34.3 module needs a declared fact requirement, even an empty one"
)

#: Non-fact inputs a module needs from the user's own record. Named so the
#: three fact-free modules are still gated on something: a family reminder with
#: no family members is not a card, it is an empty box.
MODULE_INPUTS: dict[MorningModule, tuple[str, ...]] = {
    MorningModule.PRIORITIES: ("priorities",),
    MorningModule.GOAL_CHECK: ("goals",),
    MorningModule.FAMILY_REMINDER: ("family_events",),
}


@dataclass(frozen=True)
class RankingContext:
    """Everything the ranking decision reads that is not a fact.

    `available_inputs` is the set of non-fact inputs the user actually has
    (see `MODULE_INPUTS`); `relevance` lets the caller push a contextual module
    up or down for this specific morning — a festival today, a family birthday
    tomorrow — without the ordering rules moving.
    """

    density: Density
    available_inputs: frozenset[str] = frozenset()
    relevance: dict[MorningModule, float] | None = None


@dataclass(frozen=True)
class RankedModule:
    module: MorningModule
    snapshots: tuple[FactSnapshot, ...]
    score: float = 0.0


def emittable(
    module: MorningModule,
    facts_by_kind: dict[FactKind, list[FactSnapshot]],
    context: RankingContext,
) -> bool:
    """§5.3, applied before anything is composed.

    A module passes only when its evidence is in hand: at least one of its
    declared fact kinds, and every non-fact input it needs. Everything else in
    this file is ordering; this is the part that keeps the engine honest.
    """
    for required in MODULE_INPUTS.get(module, ()):
        if required not in context.available_inputs:
            return False
    kinds = MODULE_FACT_KINDS[module]
    if not kinds:
        return True
    return any(facts_by_kind.get(kind) for kind in kinds)


def _snapshots_for(
    module: MorningModule, facts_by_kind: dict[FactKind, list[FactSnapshot]]
) -> tuple[FactSnapshot, ...]:
    """Every snapshot backing this module, in declaration order.

    All of them travel with the module, not just the first: §34.2 requires the
    full snapshot embedded at generation time, and the grounding validator
    checks the number in a sentence against the facts THAT sentence cites.
    Handing it a subset would fail valid copy.
    """
    out: list[FactSnapshot] = []
    for kind in MODULE_FACT_KINDS[module]:
        out.extend(facts_by_kind.get(kind, ()))
    return tuple(out)


def index_facts(facts: Sequence[FactSnapshot]) -> dict[FactKind, list[FactSnapshot]]:
    by_kind: dict[FactKind, list[FactSnapshot]] = {}
    for snapshot in facts:
        by_kind.setdefault(snapshot.kind, []).append(snapshot)
    return by_kind


def rank(
    facts: Sequence[FactSnapshot], context: RankingContext
) -> list[RankedModule]:
    """Select the day's modules (§7.1's "ranking engine picks from the 17").

    Order of operations, and each step is a spec line:

    1. Drop everything with no evidence (§5.3).
    2. Take the base — §28.2's core card and practical strip, always present.
    3. Take the panchang row unless density is LOW (§28.2).
    4. Rank the contextual pool by relevance and take `CONTEXTUAL_CAP` of them
       (§28.2: max 4 visible, count set by density).
    5. Add the HIGH extras at HIGH only.
    6. Return in §34.3's canonical order, so the Today screen renders the same
       sequence whatever order the ranking considered them in.
    """
    by_kind = index_facts(facts)
    relevance = context.relevance or {}

    chosen: dict[MorningModule, float] = {}

    for module in BASE_MODULES:
        if emittable(module, by_kind, context):
            chosen[module] = relevance.get(module, 1.0)

    if context.density is not Density.LOW:
        for module in PANCHANG_ROW:
            if emittable(module, by_kind, context):
                chosen[module] = relevance.get(module, 1.0)

    cap = CONTEXTUAL_CAP[context.density]
    if cap:
        eligible = [m for m in CONTEXTUAL_POOL if emittable(m, by_kind, context)]
        # Stable: relevance descending, then §34.3's own order, so two modules
        # of equal relevance always resolve the same way. A ranking that
        # reshuffled equal scores would make the Today screen jitter between
        # renders for no reason a user could see.
        eligible.sort(
            key=lambda m: (-relevance.get(m, 0.0), MORNING_MODULE_ORDER.index(m))
        )
        for module in eligible[:cap]:
            chosen[module] = relevance.get(module, 0.0)

    if context.density is Density.HIGH:
        for module in HIGH_EXTRAS:
            if emittable(module, by_kind, context):
                chosen[module] = relevance.get(module, 1.0)

    return [
        RankedModule(
            module=module,
            snapshots=_snapshots_for(module, by_kind),
            score=chosen[module],
        )
        for module in MORNING_MODULE_ORDER
        if module in chosen
    ]


def core_cards(facts: Sequence[FactSnapshot]) -> list[RankedModule]:
    """§7.1's degrade target: "verified core cards (panchang + one chart theme,
    no LLM)".

    Deliberately not `rank(..., Density.LOW)`. The degrade is narrower than the
    lowest density — it is the panchang the day is anchored on plus a single
    chart theme, and it is what ships when something has gone wrong. Reusing
    the LOW path would make a degraded brief indistinguishable from a skeptic's
    normal one, and §28.2 requires the degraded state to say so honestly
    ("Tara has the essentials today; the full reading returns shortly").
    """
    by_kind = index_facts(facts)
    context = RankingContext(density=Density.LOW)
    wanted = (
        MorningModule.MOON_NAKSHATRA_NOTE,
        MorningModule.ENERGY_OF_DAY,
        MorningModule.PERSONAL_CHART_THEME,
    )
    return [
        RankedModule(module=module, snapshots=_snapshots_for(module, by_kind), score=1.0)
        for module in MORNING_MODULE_ORDER
        if module in wanted and emittable(module, by_kind, context)
    ]
