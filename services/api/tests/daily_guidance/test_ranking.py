"""The ranking engine: §34.3's closed enum, §5.3's evidence rule, §28.2's density."""

from __future__ import annotations

import pytest
from sitara_schemas.modules import MORNING_MODULE_ORDER, MorningModule

from sitara_api.daily_guidance import ranking
from sitara_api.daily_guidance.types import Density


def context(density: Density = Density.MED, **kwargs) -> ranking.RankingContext:  # noqa: ANN003
    return ranking.RankingContext(density=density, **kwargs)


# --- §34.3: the enum is closed ---------------------------------------------


def test_the_engine_emits_only_the_seventeen(full_facts) -> None:  # noqa: ANN001
    """§34.3: "the ranking engine emits module IDs from this enum and nothing else"."""
    for density in Density:
        for item in ranking.rank(full_facts, context(density)):
            assert isinstance(item.module, MorningModule)
            assert item.module in MORNING_MODULE_ORDER


def test_every_module_of_the_seventeen_is_reachable() -> None:
    """A module in the enum that no density can emit is a module that does not
    exist. `ranking` asserts this at import; this makes the failure legible."""
    buckets = (
        set(ranking.BASE_MODULES)
        | set(ranking.PANCHANG_ROW)
        | set(ranking.CONTEXTUAL_POOL)
        | set(ranking.HIGH_EXTRAS)
    )
    assert buckets == set(MORNING_MODULE_ORDER)
    assert len(MORNING_MODULE_ORDER) == 17


def test_output_is_in_the_canonical_order(full_facts) -> None:  # noqa: ANN001
    """§34.3 fixes the order and BriefCard's 17 variants map 1:1 to it, so the
    Today screen must not depend on what order the ranking considered them."""
    ranked = ranking.rank(full_facts, context(Density.HIGH))
    positions = [MORNING_MODULE_ORDER.index(item.module) for item in ranked]
    assert positions == sorted(positions)


# --- §5.3: no fact, no module ----------------------------------------------


def test_a_module_with_no_fact_is_never_emitted() -> None:
    """§5.3 cite-or-die, applied before anything is composed."""
    assert ranking.rank([], context(Density.HIGH)) == []


def test_only_modules_backed_by_the_facts_present_are_emitted(tithi_fact) -> None:  # noqa: ANN001
    """A tithi alone supports the tithi-derived modules and nothing else."""
    emitted = {item.module for item in ranking.rank([tithi_fact], context(Density.HIGH))}
    assert MorningModule.ENERGY_OF_DAY in emitted
    assert MorningModule.COLOUR in emitted
    # No chart fact → no chart theme; no numerology fact → no number.
    assert MorningModule.PERSONAL_CHART_THEME not in emitted
    assert MorningModule.NUMBER not in emitted
    assert MorningModule.MOON_NAKSHATRA_NOTE not in emitted


def test_every_emitted_module_carries_its_snapshots(full_facts) -> None:  # noqa: ANN001
    """§34.2: the snapshot travels with the artefact, at generation time."""
    for item in ranking.rank(full_facts, context(Density.HIGH)):
        if ranking.MODULE_FACT_KINDS[item.module]:
            assert item.snapshots, f"{item.module} was emitted with no snapshot"


def test_fact_free_modules_are_gated_on_the_users_own_data() -> None:
    """The three modules with no astrological claim are still gated — on
    inputs, not on fact-IDs. A goal check with no goal is an empty box."""
    assert ranking.rank([], context(Density.MED)) == []
    ranked = ranking.rank(
        [], context(Density.MED, available_inputs=frozenset({"goals", "priorities"}))
    )
    assert {item.module for item in ranked} == {
        MorningModule.PRIORITIES,
        MorningModule.GOAL_CHECK,
    }


# --- §28.2: density changes the count, never the facts ----------------------


def test_density_changes_the_count_not_the_facts(full_facts) -> None:  # noqa: ANN001
    """§28.2: "Density changes ranking-engine output count, never facts"."""
    by_density = {
        density: ranking.rank(full_facts, context(density)) for density in Density
    }
    counts = {d: len(items) for d, items in by_density.items()}
    assert counts[Density.LOW] < counts[Density.MED] < counts[Density.HIGH]

    # The facts each shared module stands on are identical across densities.
    for module in MorningModule:
        seen = {
            tuple(i.snapshots)
            for items in by_density.values()
            for i in items
            if i.module is module
        }
        assert len(seen) <= 1, f"{module} stands on different facts at different densities"


def test_low_is_the_practical_strip_only(full_facts) -> None:  # noqa: ANN001
    """§28.2 LOW: "Tara's line + core card + practical strip only, panchang
    collapsed"."""
    emitted = {i.module for i in ranking.rank(full_facts, context(Density.LOW))}
    assert emitted <= set(ranking.BASE_MODULES)
    assert MorningModule.MOON_NAKSHATRA_NOTE not in emitted  # panchang collapsed


def test_med_adds_the_panchang_row_and_two_contextual_cards(full_facts) -> None:  # noqa: ANN001
    """§28.2 MED: "+ 2 contextual cards + panchang row"."""
    emitted = [i.module for i in ranking.rank(full_facts, context(Density.MED))]
    assert MorningModule.MOON_NAKSHATRA_NOTE in emitted
    contextual = [m for m in emitted if m in ranking.CONTEXTUAL_POOL]
    assert len(contextual) == 2


def test_high_never_shows_more_than_four_contextual_cards(full_facts) -> None:  # noqa: ANN001
    """§28.2: "contextual cards ranked by the engine (max 4 visible)"."""
    emitted = [i.module for i in ranking.rank(full_facts, context(Density.HIGH))]
    contextual = [m for m in emitted if m in ranking.CONTEXTUAL_POOL]
    assert len(contextual) <= 4


def test_relevance_orders_the_contextual_cards(full_facts) -> None:  # noqa: ANN001
    """A festival today should out-rank a food note; the caller says so with a
    relevance score and the ordering rules do not move."""
    ranked = ranking.rank(
        full_facts,
        context(Density.MED, relevance={MorningModule.FESTIVAL_OBSERVANCE: 9.0}),
    )
    # No festival fact in the fixture, so it cannot be chosen even at 9.0 —
    # relevance ranks the eligible, it never makes a module eligible.
    assert MorningModule.FESTIVAL_OBSERVANCE not in {i.module for i in ranked}


def test_equal_relevance_resolves_deterministically(full_facts) -> None:  # noqa: ANN001
    """A ranking that reshuffled equal scores would make Today jitter between
    renders for no reason a user could see."""
    runs = {
        tuple(i.module for i in ranking.rank(full_facts, context(Density.MED)))
        for _ in range(20)
    }
    assert len(runs) == 1


# --- §7.1's degrade target -------------------------------------------------


def test_core_cards_are_panchang_plus_one_chart_theme(full_facts) -> None:  # noqa: ANN001
    """§7.1: "verified core cards (panchang + one chart theme, no LLM)"."""
    emitted = [i.module for i in ranking.core_cards(full_facts)]
    assert MorningModule.PERSONAL_CHART_THEME in emitted
    assert MorningModule.MOON_NAKSHATRA_NOTE in emitted
    assert len(emitted) <= 3


def test_core_cards_are_not_simply_the_low_density_brief(full_facts) -> None:  # noqa: ANN001
    """§28.2 requires the degraded state to be visibly different from a
    skeptic's normal morning — it says so on the card."""
    low = {i.module for i in ranking.rank(full_facts, context(Density.LOW))}
    core = {i.module for i in ranking.core_cards(full_facts)}
    assert core != low


def test_core_cards_degrade_to_nothing_rather_than_to_invention() -> None:
    assert ranking.core_cards([]) == []


@pytest.mark.parametrize("module", list(MorningModule))
def test_every_module_declares_a_fact_requirement(module: MorningModule) -> None:
    assert module in ranking.MODULE_FACT_KINDS
