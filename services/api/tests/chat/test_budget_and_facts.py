"""§9 token budgets and §5.3 step 6 fact validation."""

import datetime as dt

import pytest
from sitara_schemas.facts import ConfidenceState, Graha

from sitara_api.chat_orchestration.budget import ContextBudget, daily_cap_notice
from sitara_api.chat_orchestration.config import ChatSettings
from sitara_api.chat_orchestration.facts import validate
from sitara_api.chat_orchestration.llm import LLMUnavailable
from tests.chat.conftest import NOW, SATURN_FACT_ID, VENUS_FACT_ID, ScriptedLLM, transit_house_fact


def _settings(**overrides) -> ChatSettings:  # noqa: ANN003
    return ChatSettings(anthropic_api_key="k", **overrides)


def _history(turns: int, words: int = 40) -> list[dict[str, str]]:
    return [
        {"role": "user" if i % 2 == 0 else "assistant", "content": "word " * words}
        for i in range(turns)
    ]


@pytest.mark.asyncio
async def test_a_short_conversation_is_sent_verbatim() -> None:
    llm = ScriptedLLM()
    plan = await ContextBudget(_settings(), llm).plan(
        history=_history(4), summary=None, locale="en"
    )

    assert len(plan.history) == 4
    assert plan.summary is None
    assert not plan.summary_refreshed
    assert llm.calls == []


@pytest.mark.asyncio
async def test_older_turns_roll_into_a_summary() -> None:
    """§9: "rolling conversation summary (Haiku) keeps context <8K tokens"."""
    llm = ScriptedLLM()
    llm.script("summary.rolling", "She is preparing for a move to Pune in September.")
    settings = _settings(history_keep_turns=4)

    plan = await ContextBudget(settings, llm).plan(
        history=_history(12), summary=None, locale="en"
    )

    assert len(plan.history) == 4
    assert plan.summary_refreshed
    assert "Pune" in (plan.summary or "")
    assert plan.estimated_tokens < settings.context_token_budget


@pytest.mark.asyncio
async def test_a_failed_summary_truncates_rather_than_blowing_the_window() -> None:
    llm = ScriptedLLM()
    llm.script("summary.rolling", LLMUnavailable("down"))

    plan = await ContextBudget(_settings(history_keep_turns=4), llm).plan(
        history=_history(12), summary="earlier: she asked about work", locale="en"
    )

    assert len(plan.history) == 4
    assert not plan.summary_refreshed
    assert plan.summary == "earlier: she asked about work"


def test_the_daily_cap_is_a_notice_not_a_block() -> None:
    """§29.2 forbids dark patterns; cutting someone off mid-conversation to
    protect a cost line would be one."""
    settings = _settings(daily_soft_cap_tokens=1000)

    assert daily_cap_notice(settings, 500) is None
    assert daily_cap_notice(settings, 1500) == "chat.budget.daily_soft_cap"


# --------------------------------------------------------------------------
# Fact validation
# --------------------------------------------------------------------------


def test_valid_facts_survive() -> None:
    facts = validate([transit_house_fact(Graha.SATURN, 10, SATURN_FACT_ID)], NOW)

    assert facts.fact_ids == (SATURN_FACT_ID,)
    assert facts.rejected == ()


def test_a_stale_transit_is_rejected() -> None:
    """A yesterday's transit served as today's is as wrong as an invented one."""
    stale = transit_house_fact(Graha.SATURN, 10, SATURN_FACT_ID)
    tomorrow = NOW + dt.timedelta(days=2)

    facts = validate([stale], tomorrow)

    assert facts.snapshots == ()
    assert facts.rejected == (f"{SATURN_FACT_ID}:stale",)


def test_duplicates_are_dropped() -> None:
    snapshot = transit_house_fact(Graha.SATURN, 10, SATURN_FACT_ID)

    facts = validate([snapshot, snapshot], NOW)

    assert len(facts.snapshots) == 1
    assert facts.rejected == (f"{SATURN_FACT_ID}:duplicate",)


def test_a_not_calculable_fact_never_reaches_interpretation() -> None:
    """§5.3 step 7: only validated fact-IDs are passed on."""
    snapshot = transit_house_fact(Graha.VENUS, 7, VENUS_FACT_ID).model_copy(
        update={"confidence": ConfidenceState.CANNOT_CALCULATE}
    )

    facts = validate([snapshot], NOW)

    assert facts.snapshots == ()
    assert facts.rejected == (f"{VENUS_FACT_ID}:not_calculable",)


def test_by_id_finds_a_served_snapshot() -> None:
    facts = validate([transit_house_fact(Graha.SATURN, 10, SATURN_FACT_ID)], NOW)

    assert facts.by_id(SATURN_FACT_ID) is not None
    assert facts.by_id(VENUS_FACT_ID) is None
