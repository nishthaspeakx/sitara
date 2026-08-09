"""Composition, citations, and the grounding gate over the polish (§7.1, §5.3).

The composed text is the thing the whole degrade ladder rests on: if it is true
before the model touches it, then "reject the polish" is always a safe answer.
So these tests check the composed text against the SAME validator that gates
the polished text, which is the strongest statement available — the engine's
own sentences pass cite-or-die.
"""

from __future__ import annotations

import json

import pytest
from sitara_schemas.modules import MorningModule

from sitara_api.chat_orchestration.grounding import GroundingValidator, strip_citations
from sitara_api.chat_orchestration.llm import (
    LLMRequest,
    LLMResponse,
    LLMUnavailable,
)
from sitara_api.daily_guidance import ranking
from sitara_api.daily_guidance.polish import BriefPolisher
from sitara_api.daily_guidance.templates import BriefComposer, template_id
from sitara_api.daily_guidance.types import Density

LOCALES = ("en", "hi", "hi-Latn")


def compose(facts, locale: str, density: Density = Density.HIGH, inputs=None):  # noqa: ANN001, ANN201
    context = ranking.RankingContext(
        density=density, available_inputs=frozenset(inputs or {})
    )
    ranked = ranking.rank(facts, context)
    return BriefComposer(inputs=inputs).compose_all(ranked, locale)


# --- composition -----------------------------------------------------------


@pytest.mark.parametrize("locale", LOCALES)
def test_every_composed_module_passes_the_grounding_validator(full_facts, locale) -> None:  # noqa: ANN001
    """The engine's own sentences satisfy §5.3 — cited, numbers verbatim.

    This is what makes §7.1's degrade safe: falling back to composed text can
    never ship an uncited claim, because composed text is where the citations
    come from.
    """
    validator = GroundingValidator()
    modules = compose(full_facts, locale)
    assert modules, f"{locale}: nothing composed from a full fact set"
    for module in modules:
        verdict = validator.check(module.text, module.snapshots, locale)
        assert verdict.ok, f"{locale} {module.module}: {verdict.reasons}"


@pytest.mark.parametrize("locale", LOCALES)
def test_composed_claims_carry_a_citation(full_facts, locale) -> None:  # noqa: ANN001
    for module in compose(full_facts, locale):
        if module.snapshots:
            assert "[[fact:" in module.text, f"{module.module} composed uncited"
            for snapshot in module.snapshots:
                assert snapshot.fact_id in module.text or len(module.snapshots) > 1


@pytest.mark.parametrize("locale", LOCALES)
def test_citations_never_reach_the_reader(full_facts, locale) -> None:  # noqa: ANN001
    """§30.4: fact-IDs are internal and never render."""
    for module in compose(full_facts, locale):
        assert "[[fact:" not in strip_citations(module.text)


@pytest.mark.parametrize("locale", LOCALES)
def test_times_render_in_the_facts_own_zone(full_facts, locale) -> None:  # noqa: ANN001
    """The rahu-kaal fixture is 09:00–10:30 IST. A brief that rendered it in
    UTC would be wrong AND would fail its own numeric check."""
    modules = {m.module: m for m in compose(full_facts, locale)}
    caution = modules[MorningModule.CAUTION_WINDOW]
    assert "09:00" in caution.text and "10:30" in caution.text
    assert "03:30" not in caution.text  # the UTC rendering


def test_a_module_whose_term_is_missing_in_locale_is_dropped(nakshatra_fact) -> None:
    """§2.4: no silent English fallback, ever. An unnameable card is not a card."""
    composer = BriefComposer()
    ranked = ranking.RankedModule(
        module=MorningModule.MOON_NAKSHATRA_NOTE, snapshots=(nakshatra_fact,)
    )
    assert composer.compose(ranked, "en") is not None
    # `ta` has no catalog and no family fallback to one, so the term cannot be
    # rendered and the module declines rather than emitting English.
    assert composer.compose(ranked, "ta") is None


def test_the_moon_note_cites_the_moon_and_never_another_graha(
    nakshatra_fact,  # noqa: ANN001
) -> None:
    """The bug the M6 acceptance harness caught on its first run.

    `natal.graha.nakshatra` is emitted for all NINE grahas and the Sun's comes
    first, so taking the first nakshatra-shaped value produced "The Moon sits
    in Purva Bhadrapada today" citing the SUN's nakshatra. Cited, in the served
    payload, numbers matching — and false. No validator can catch it: the
    citation machinery checks that a sentence stands on a fact, not that it
    stands on the RIGHT one, so the reader has to.
    """
    import datetime as dt

    from sitara_schemas.facts import (
        FactKind,
        FactMethod,
        FactPrecision,
        FactSnapshot,
        Graha,
        Nakshatra,
        NakshatraValue,
        TzMethod,
        build_fact_id,
    )

    def natal_nakshatra(graha: Graha, nakshatra: Nakshatra, index: int) -> FactSnapshot:
        return FactSnapshot(
            fact_id=build_fact_id(
                f"natal.{graha.value}.nakshatra", "natal", "6a70000000000000000000a1", 1
            ),
            kind=FactKind.NATAL_GRAHA_NAKSHATRA,
            value=NakshatraValue(
                graha=graha, nakshatra=nakshatra, nakshatra_index=index, pada=1
            ),
            precision=FactPrecision(tolerance=0, unit="exact"),
            method=FactMethod(
                ayanamsa="lahiri",
                tz=TzMethod(tz="Asia/Kolkata", utc_offset_seconds=19800),
            ),
            valid_from=dt.datetime(2026, 8, 12, tzinfo=dt.UTC),
            valid_to=None,
            engine_semver="0.1.0",
            data_revision="test",
        )

    # The Sun first, exactly as the engine returns them.
    facts = [
        natal_nakshatra(Graha.SUN, Nakshatra.PURVA_BHADRAPADA, 25),
        natal_nakshatra(Graha.MOON, Nakshatra.ROHINI, 4),
    ]
    composer = BriefComposer()
    ranked = ranking.RankedModule(
        module=MorningModule.MOON_NAKSHATRA_NOTE, snapshots=tuple(facts)
    )
    composed = composer.compose(ranked, "en")
    assert composed is not None
    assert "Rohini" in composed.text, "the card must name the MOON's nakshatra"
    assert "Purva Bhadrapada" not in composed.text
    assert composed.fact_ids == (facts[1].fact_id,), "and cite the Moon's fact"


def test_the_moon_note_declines_when_only_other_grahas_are_known() -> None:
    """No Moon nakshatra, no card. Falling back to another body's would be the
    same false sentence with a different name in it."""
    import datetime as dt

    from sitara_schemas.facts import (
        FactKind,
        FactMethod,
        FactPrecision,
        FactSnapshot,
        Graha,
        Nakshatra,
        NakshatraValue,
        build_fact_id,
    )

    sun_only = FactSnapshot(
        fact_id=build_fact_id("natal.sun.nakshatra", "natal", "6a70000000000000000000a1", 1),
        kind=FactKind.NATAL_GRAHA_NAKSHATRA,
        value=NakshatraValue(
            graha=Graha.SUN, nakshatra=Nakshatra.PURVA_BHADRAPADA, nakshatra_index=25, pada=1
        ),
        precision=FactPrecision(tolerance=0, unit="exact"),
        method=FactMethod(ayanamsa="lahiri"),
        valid_from=dt.datetime(2026, 8, 12, tzinfo=dt.UTC),
        valid_to=None,
        engine_semver="0.1.0",
        data_revision="test",
    )
    ranked = ranking.RankedModule(
        module=MorningModule.MOON_NAKSHATRA_NOTE, snapshots=(sun_only,)
    )
    assert BriefComposer().compose(ranked, "en") is None


def test_fact_free_modules_compose_without_a_citation() -> None:
    """A priority nudge repeats what the user said; it asserts nothing about
    the sky, and the grounding validator agrees."""
    modules = compose([], "en", inputs={"priorities": "the lease decision"})
    assert [m.module for m in modules] == [MorningModule.PRIORITIES]
    assert "[[fact:" not in modules[0].text
    verdict = GroundingValidator().check(modules[0].text, (), "en")
    assert verdict.ok, verdict.reasons


def test_template_ids_are_versioned(full_facts) -> None:  # noqa: ANN001
    """§23.8 reports per template version; two renderings must be tellable apart."""
    for module in compose(full_facts, "en"):
        assert module.template_id == template_id(module.module)
        assert module.template_id.startswith("brief-v1.")


# --- the polish gate -------------------------------------------------------


class ScriptedLLM:
    """Returns whatever the test tells it to, and records what it was asked."""

    def __init__(self, *responses: LLMResponse | Exception) -> None:
        self._responses: list[LLMResponse | Exception] = list(responses)
        self.requests: list[LLMRequest] = []

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if not self._responses:
            raise LLMUnavailable("scripted: exhausted")
        nxt = self._responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


def response_for(modules, transform) -> LLMResponse:  # noqa: ANN001
    payload = {
        "lines": [{"index": i, "text": transform(m)} for i, m in enumerate(modules)]
    }
    return LLMResponse(
        text=json.dumps(payload), model="test", parsed=payload
    )


@pytest.mark.asyncio()
async def test_a_faithful_polish_is_accepted(full_facts) -> None:  # noqa: ANN001
    modules = compose(full_facts, "en", Density.MED)
    llm = ScriptedLLM(response_for(modules, lambda m: f"Gently: {m.text}"))
    polished, report = await BriefPolisher(llm).polish(modules, "en", Density.MED)

    assert report.accepted == len(modules)
    assert report.rejected == 0
    assert all(m.polished_text and m.polished_text.startswith("Gently:") for m in polished)
    assert all("[[fact:" not in (m.polished_text or "") for m in polished)


@pytest.mark.asyncio()
async def test_a_polish_that_drops_its_citation_is_rejected(full_facts) -> None:  # noqa: ANN001
    """Failure mode 1: the model rewrites the sentence and loses the marker."""
    modules = compose(full_facts, "en", Density.LOW)
    stripped = response_for(modules, lambda m: strip_citations(m.text))
    llm = ScriptedLLM(stripped, stripped)  # fails, then fails its regeneration
    polished, report = await BriefPolisher(llm).polish(modules, "en", Density.LOW)

    assert report.accepted == 0
    assert report.regenerated is True
    assert report.all_rejected is True
    # The composed text survives — a spoiled line falls back to the engine's own.
    assert all(m.polished_text is None for m in polished)
    assert [m.text for m in polished] == [m.text for m in modules]


@pytest.mark.asyncio()
async def test_a_polish_that_invents_a_fact_id_is_rejected(full_facts) -> None:  # noqa: ANN001
    """Failure mode 2: the fabricated transit, which reads like a real one.

    The invented id is added ALONGSIDE the real one, so the structural check
    (did this line keep its own citation?) passes and the case falls to the
    grounding validator, which is the layer that owns "is this id one we
    served?". Replacing the real id instead would be caught a step earlier and
    would leave this path untested.
    """
    modules = compose(full_facts, "en", Density.LOW)
    fake = "[[fact:transit.jupiter.house/2026-08-12/6a70000000000000000000a1@v1]]"
    bad = response_for(modules, lambda m: f"{m.text} {fake}")
    llm = ScriptedLLM(bad, bad)
    _, report = await BriefPolisher(llm).polish(modules, "en", Density.LOW)

    assert report.accepted == 0
    assert any("not in the served payload" in r for r in report.reasons)


@pytest.mark.asyncio()
async def test_a_line_that_returns_uncited_is_rejected_even_with_no_astrology_words(
    abhijit_fact,  # noqa: ANN001
) -> None:
    """The gap the structural check closes.

    "A good window opens between 11:48 and 12:36" names no graha, rashi or
    tradition term, so `GroundingValidator` — which decides claim-hood from
    vocabulary, the only signal free-form chat has — does not gate it. In a
    template that is not an edge case, it is every morning. The brief knows the
    line was composed FROM facts, so it can require the citation structurally.
    """
    modules = compose([abhijit_fact], "en", Density.LOW)
    window = [m for m in modules if m.module is MorningModule.FAVOURABLE_WINDOW]
    assert window, "the fixture should support a favourable window"

    # Proof the vocabulary-based validator alone would let it through.
    bare = strip_citations(window[0].text)
    assert GroundingValidator().check(bare, window[0].snapshots, "en").ok

    stripped = response_for(window, lambda m: strip_citations(m.text))
    llm = ScriptedLLM(stripped, stripped)
    _, report = await BriefPolisher(llm).polish(window, "en", Density.LOW)
    assert report.accepted == 0
    assert any("lost the citation" in r for r in report.reasons)


@pytest.mark.asyncio()
async def test_a_polish_that_changes_a_number_is_rejected(full_facts) -> None:  # noqa: ANN001
    """Failure mode 3: §5.3's numbers-verbatim rule. 10th house becomes 8th."""
    modules = [m for m in compose(full_facts, "en", Density.LOW)
               if m.module is MorningModule.PERSONAL_CHART_THEME]
    assert modules, "fixture should support a chart theme"
    bad = response_for(modules, lambda m: m.text.replace("10th", "8th"))
    llm = ScriptedLLM(bad, bad)
    _, report = await BriefPolisher(llm).polish(modules, "en", Density.LOW)

    assert report.accepted == 0
    assert any("does not appear in the cited fact" in r for r in report.reasons)


@pytest.mark.asyncio()
async def test_exactly_one_corrective_regeneration(full_facts) -> None:  # noqa: ANN001
    """§9 fixes it at one, and the brief inherits it rather than inventing a
    second policy."""
    modules = compose(full_facts, "en", Density.LOW)
    bad = response_for(modules, lambda m: strip_citations(m.text))
    llm = ScriptedLLM(bad, bad, bad)
    await BriefPolisher(llm).polish(modules, "en", Density.LOW)
    assert len(llm.requests) == 2  # the attempt and its ONE regeneration


@pytest.mark.asyncio()
async def test_one_bad_line_does_not_cost_the_others_their_polish(full_facts) -> None:  # noqa: ANN001
    modules = compose(full_facts, "en", Density.MED)
    assert len(modules) > 2

    def transform(index_holder=[0]):  # noqa: B006
        def inner(m):  # noqa: ANN001
            index_holder[0] += 1
            if index_holder[0] == 1:
                return strip_citations(m.text)  # spoil exactly one
            return f"Gently: {m.text}"

        return inner

    good = response_for(modules, transform())
    llm = ScriptedLLM(good, good)
    polished, report = await BriefPolisher(llm).polish(modules, "en", Density.MED)
    assert report.accepted == len(modules) - 1
    assert report.all_rejected is False


@pytest.mark.asyncio()
async def test_a_provider_outage_is_not_a_grounding_failure(full_facts) -> None:  # noqa: ANN001
    """§8 degrades an outage gracefully; the composed text is already verified.
    Conflating the two would degrade a perfectly good brief to core cards every
    time Anthropic had a bad minute."""
    modules = compose(full_facts, "en", Density.MED)
    llm = ScriptedLLM(LLMUnavailable("down"))
    polished, report = await BriefPolisher(llm).polish(modules, "en", Density.MED)

    assert report.unavailable is True
    assert report.all_rejected is False  # NOT the degrade condition
    assert [m.text for m in polished] == [m.text for m in modules]


@pytest.mark.asyncio()
async def test_the_cached_prefix_is_shared_across_users(full_facts) -> None:  # noqa: ANN001
    """§9/§7.1: the stable prefix is what makes the Claude call the only
    per-user marginal cost. Two users at one locale must send the identical
    system blocks, and the breakpoint must sit after the last of them."""
    modules = compose(full_facts, "en", Density.MED)
    first, second = ScriptedLLM(), ScriptedLLM()
    await BriefPolisher(first).polish(modules, "en", Density.LOW)
    await BriefPolisher(second).polish(modules, "en", Density.HIGH)

    a, b = first.requests[0], second.requests[0]
    assert a.system == b.system, "density must not vary the cached prefix"
    assert a.cacheable_prefix_len == len(a.system)
    # The per-brief material rides BELOW the breakpoint.
    assert all("density_note" not in block for block in a.system)
    assert "density_note" in a.messages[0]["content"]


@pytest.mark.asyncio()
async def test_the_declared_temperature_is_9s_guidance_value(full_facts) -> None:  # noqa: ANN001
    """§37 (CC-004): the stage DECLARES 0.2; whether it is sent is the
    adapter's decision. Deleting the declaration is what the entry forbids."""
    modules = compose(full_facts, "en", Density.MED)
    llm = ScriptedLLM()
    await BriefPolisher(llm).polish(modules, "en", Density.MED)
    assert llm.requests[0].temperature == 0.2


@pytest.mark.asyncio()
async def test_the_whole_brief_is_one_call(full_facts) -> None:  # noqa: ANN001
    """§7.1: "LLM polish (batched…)". One call per brief, not one per module."""
    modules = compose(full_facts, "en", Density.HIGH)
    assert len(modules) > 5
    llm = ScriptedLLM(response_for(modules, lambda m: f"Gently: {m.text}"))
    await BriefPolisher(llm).polish(modules, "en", Density.HIGH)
    assert len(llm.requests) == 1
