"""§8 degradation vs §9 validator failure — they look alike and must not be.

Both end at the safe fallback line. Only one of them is a safety event, and
confusing the two would bury real L4 events under provider flapping in a queue
with a 24h SLA (§22.9).
"""

import pytest

from sitara_api.chat_orchestration.llm import AnthropicLLM, LLMResponse, LLMUnavailable
from sitara_api.chat_orchestration.pipeline import KEY_FALLBACK
from sitara_api.chat_orchestration.prompts import build_system
from sitara_api.chat_orchestration.types import (
    RiskClass,
    SafetyAssessment,
    SafetyLevel,
    Stage,
)
from tests.chat.conftest import SATURN_FACT_ID, build_env, run_turn

GROUNDED = (
    "Saturn is moving through your 10th house today, "
    f"so work themes rise [[{SATURN_FACT_ID}]]."
)


@pytest.mark.asyncio
async def test_a_model_outage_serves_the_fallback_without_queueing_a_human() -> None:
    """§8 calls a provider outage a degradation. §22.9's queue is for safety
    review, and an outage is not one."""
    env = build_env()
    env.llm.script("generate", LLMUnavailable("down"))

    result = await run_turn(env, "How's my work looking today?")

    assert result.message_key == KEY_FALLBACK
    assert not result.review_queued
    assert env.review_queue.entries == []
    assert env.trace.spans_for(Stage.GENERATION)[0]["status"] == "failed"


@pytest.mark.asyncio
async def test_a_validator_failure_does_queue_a_human() -> None:
    """The contrast case — same fallback text, different meaning."""
    env = build_env()
    uncited = "Saturn is transiting your 10th house today."
    env.llm.script("generate", uncited, uncited)

    result = await run_turn(env, "How's my work looking today?")

    assert result.message_key == KEY_FALLBACK
    assert result.review_queued
    assert env.review_queue.entries[0].stage is Stage.GROUNDING


@pytest.mark.asyncio
async def test_a_truncated_reply_is_regenerated_for_brevity_not_citations() -> None:
    """§9's per-turn cap can cut off the closing citation. Blaming the
    citations would spend the one regeneration on the wrong instruction."""
    env = build_env()
    env.llm.script(
        "generate",
        LLMResponse(
            text="Saturn is moving through your 10th house and this month brings",
            model="scripted",
            truncated=True,
            input_tokens=100,
            output_tokens=1024,
        ),
        GROUNDED,
    )

    result = await run_turn(env, "How's my work looking today?")

    assert result.regenerations == 1
    assert not result.review_queued
    assert env.trace.spans_for(Stage.GENERATION)[0]["status"] == "truncated"
    correction = env.llm.calls[-1].messages[-1]["content"]
    assert "token cap" in correction


@pytest.mark.asyncio
async def test_a_memory_failure_degrades_the_turn_instead_of_failing_it() -> None:
    """Memory is context, not correctness — the facts side already works
    this way and the two must not diverge."""

    class BrokenRetriever:
        async def retrieve(self, **_: object):  # noqa: ANN003
            raise RuntimeError("vector search down")

    env = build_env()
    env.pipeline._memory = BrokenRetriever()  # noqa: SLF001 — wiring a fault
    env.llm.script("generate", GROUNDED)

    result = await run_turn(env, "How's my work looking today?")

    assert result.fact_ids == (SATURN_FACT_ID,)
    assert not result.review_queued


def test_the_cache_breakpoint_never_sits_on_the_safety_register() -> None:
    """§9 caches persona + style guide. The register varies per turn, so a
    breakpoint below it would make every constrained turn a cache WRITE."""
    constrained = build_system(
        "en", SafetyAssessment(level=SafetyLevel.L3_REDIRECT, risk_class=RiskClass.MEDICAL)
    )
    blocks = AnthropicLLM._system_blocks(  # noqa: SLF001
        constrained.blocks, constrained.cacheable_prefix_len
    )

    marked = [i for i, block in enumerate(blocks) if "cache_control" in block]
    assert marked == [constrained.cacheable_prefix_len - 1]
    assert "CONSTRAINED MODE" in blocks[-1]["text"]
    assert "cache_control" not in blocks[-1]


def test_an_unconstrained_turn_caches_the_whole_prefix() -> None:
    clear = build_system("en", SafetyAssessment(SafetyLevel.L1_CLEAR, RiskClass.NONE))
    blocks = AnthropicLLM._system_blocks(clear.blocks, clear.cacheable_prefix_len)  # noqa: SLF001

    assert "cache_control" in blocks[-1]
    assert clear.cacheable_prefix_len == len(clear.blocks)
