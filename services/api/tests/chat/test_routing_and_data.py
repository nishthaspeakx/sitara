"""§22.8 tool allowlist, §5.3 required-data, §5.4 confidence."""

import pytest
from sitara_schemas.facts import ConfidenceState, FactSource, Graha

from sitara_api.chat_orchestration import required_data
from sitara_api.chat_orchestration.config import ChatSettings
from sitara_api.chat_orchestration.intent import IntentRouter
from sitara_api.chat_orchestration.llm import LLMUnavailable
from sitara_api.chat_orchestration.types import (
    BirthProfile,
    FactTool,
    Intent,
    IntentDecision,
    RiskClass,
    SafetyAssessment,
    SafetyLevel,
    ValidatedFacts,
)
from tests.chat.conftest import (
    SATURN_FACT_ID,
    ScriptedLLM,
    transit_house_fact,
)

CLEAR = SafetyAssessment(level=SafetyLevel.L1_CLEAR, risk_class=RiskClass.NONE)
CONSTRAINED = SafetyAssessment(level=SafetyLevel.L2_CONSTRAINED, risk_class=RiskClass.NONE)


def _router(llm: ScriptedLLM) -> IntentRouter:
    return IntentRouter(ChatSettings(anthropic_api_key="k"), llm)


@pytest.mark.asyncio
async def test_a_tool_outside_the_intents_allowlist_is_dropped() -> None:
    """§22.8: "a casual-chat turn cannot invoke billing tools" — enforced in
    code after the model has spoken, not by asking it nicely."""
    llm = ScriptedLLM()
    llm.script(
        "intent.route",
        {
            "intent": "greeting_smalltalk",
            "confidence": 0.9,
            "tools": ["transits", "muhurat_window"],
            "slots": {},
        },
    )
    decision = await _router(llm).route("hi Tara", "en", CLEAR)

    assert decision.intent is Intent.GREETING_SMALLTALK
    assert decision.tools == ()


@pytest.mark.asyncio
async def test_allowed_tools_survive() -> None:
    llm = ScriptedLLM()
    llm.script(
        "intent.route",
        {
            "intent": "timing_question",
            "confidence": 0.8,
            "tools": ["muhurat_window", "natal_chart"],
            "slots": {"occasion": "marriage"},
        },
    )
    decision = await _router(llm).route("when should we marry?", "en", CLEAR)

    # muhurat is allowed for a timing question; natal_chart is not.
    assert decision.tools == (FactTool.MUHURAT_WINDOW,)
    assert decision.slots == {"occasion": "marriage"}


@pytest.mark.asyncio
async def test_a_constrained_turn_is_never_routed_to_astrology() -> None:
    """§9: astrology framing is REMOVED at L2+ — the tools are not merely
    denied later, the routing question does not arise."""
    llm = ScriptedLLM()
    decision = await _router(llm).route("I'm struggling", "en", CONSTRAINED)

    assert decision.intent is Intent.EMOTIONAL_SUPPORT
    assert decision.tools == ()
    assert llm.calls == []  # no model call at all


@pytest.mark.asyncio
async def test_an_unroutable_turn_becomes_unclear_not_a_guess() -> None:
    llm = ScriptedLLM()
    llm.script("intent.route", LLMUnavailable("down"))
    decision = await _router(llm).route("hmm", "en", CLEAR)

    assert decision.intent is Intent.UNCLEAR
    assert decision.tools == ()


@pytest.mark.asyncio
async def test_an_intent_outside_the_closed_set_is_refused() -> None:
    llm = ScriptedLLM()
    llm.script("intent.route", {"intent": "tarot_reading", "confidence": 1.0, "tools": []})
    decision = await _router(llm).route("read my cards", "en", CLEAR)

    assert decision.intent is Intent.UNCLEAR


# --------------------------------------------------------------------------
# Required data → §5.4 confidence
# --------------------------------------------------------------------------


def _decision(intent: Intent, *tools: FactTool) -> IntentDecision:
    return IntentDecision(intent=intent, confidence=0.9, tools=tools)


@pytest.mark.parametrize(
    ("profile", "expected"),
    [
        (
            BirthProfile(has_date=True, has_exact_time=True, has_place=True),
            ConfidenceState.VERIFIED,
        ),
        (
            BirthProfile(has_date=True, has_place=True),
            ConfidenceState.VERIFIED_LIMITED_BIRTH_DATA,
        ),
        (
            BirthProfile(has_date=True, has_time_window=True, has_place=True),
            ConfidenceState.APPROXIMATE,
        ),
        (BirthProfile(has_place=True), ConfidenceState.CANNOT_CALCULATE),
    ],
)
def test_the_five_confidence_states(profile: BirthProfile, expected: ConfidenceState) -> None:
    sufficiency = required_data.assess(
        _decision(Intent.NATAL_CHART_QUESTION, FactTool.TRANSITS),
        profile,
        has_current_location=True,
    )

    assert sufficiency.confidence is expected


def test_a_panchang_only_turn_is_tradition_based_general() -> None:
    sufficiency = required_data.assess(
        _decision(Intent.PANCHANG_LOOKUP, FactTool.PANCHANG_DAY),
        BirthProfile(),
        has_current_location=True,
    )

    assert sufficiency.confidence is ConfidenceState.TRADITION_BASED_GENERAL
    assert sufficiency.can_answer


def test_numerology_needs_no_birth_time() -> None:
    """§5.5: the date alone is exact, so nothing here is approximate."""
    sufficiency = required_data.assess(
        _decision(Intent.NUMEROLOGY_QUESTION, FactTool.NUMEROLOGY_PROFILE),
        BirthProfile(has_date=True),
        has_current_location=False,
    )

    assert sufficiency.confidence is ConfidenceState.VERIFIED


def test_missing_fields_are_named_so_tara_can_ask() -> None:
    sufficiency = required_data.assess(
        _decision(Intent.TIMING_QUESTION, FactTool.PANCHANG_DAY_TIMINGS),
        BirthProfile(has_date=True),
        has_current_location=False,
    )

    assert sufficiency.confidence is ConfidenceState.CANNOT_CALCULATE
    assert "current_location" in sufficiency.missing


def test_a_disputed_fact_caps_the_turn_at_approximate() -> None:
    """§5.4's "disputed fact in play" row, computed at step 6."""
    facts = ValidatedFacts(
        snapshots=(transit_house_fact(Graha.SATURN, 10, SATURN_FACT_ID),), disputed=True
    )

    assert (
        required_data.downgrade_for_facts(ConfidenceState.VERIFIED, facts)
        is ConfidenceState.APPROXIMATE
    )


def test_confidence_is_never_promoted() -> None:
    clean = ValidatedFacts(snapshots=(transit_house_fact(Graha.SATURN, 10, SATURN_FACT_ID),))

    assert (
        required_data.downgrade_for_facts(ConfidenceState.TRADITION_BASED_GENERAL, clean)
        is ConfidenceState.TRADITION_BASED_GENERAL
    )


def test_a_snapshots_own_confidence_can_downgrade_the_turn() -> None:
    """A Prokerala-served fact arrives already marked Approximate (§8 ladder);
    the turn must inherit that, not out-vote it."""
    snapshot = transit_house_fact(Graha.SATURN, 10, SATURN_FACT_ID).model_copy(
        update={"confidence": ConfidenceState.APPROXIMATE, "source": FactSource.PROKERALA}
    )

    assert (
        required_data.downgrade_for_facts(ConfidenceState.VERIFIED, ValidatedFacts((snapshot,)))
        is ConfidenceState.APPROXIMATE
    )
