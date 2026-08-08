"""The §9 pipeline end to end — order, short-circuits, persistence, tracing."""

import pytest
from sitara_schemas.facts import ConfidenceState, Graha

from sitara_api.chat_orchestration.pipeline import (
    KEY_CANNOT_CALCULATE,
    KEY_CRISIS,
    KEY_MISSING_BIRTH_DATE,
)
from sitara_api.chat_orchestration.types import (
    BirthProfile,
    FactTool,
    Intent,
    PresenceState,
    SafetyLevel,
    Stage,
)
from tests.chat.conftest import (
    SATURN_FACT_ID,
    USER_ID,
    build_env,
    run_turn,
    transit_house_fact,
)

GROUNDED = (
    "Saturn is moving through your 10th house today, "
    f"so work themes rise [[{SATURN_FACT_ID}]]."
)


@pytest.mark.asyncio
async def test_happy_path(pipeline_env) -> None:
    pipeline_env.llm.script("generate", GROUNDED)

    result = await run_turn(pipeline_env, "How's my work looking today?")

    assert result.confidence is ConfidenceState.VERIFIED
    assert result.safety.level is SafetyLevel.L1_CLEAR
    assert result.presence_state is PresenceState.CALM_GUIDANCE
    assert result.regenerations == 0
    assert not result.review_queued
    assert result.fact_ids == (SATURN_FACT_ID,)
    assert "[[" not in result.text


@pytest.mark.asyncio
async def test_stage_order_is_the_spec_order(pipeline_env) -> None:
    """§9's pipeline is a sequence, and the trace is where that is checkable."""
    pipeline_env.llm.script("generate", GROUNDED)

    await run_turn(pipeline_env, "How's my work looking today?")

    seen = [event["stage"] for event in pipeline_env.trace.events if "stage" in event]
    expected = [
        Stage.LANGUAGE_DETECT,
        Stage.SAFETY_PRE,
        Stage.INTENT,
        Stage.REQUIRED_DATA,
        Stage.MEMORY_RETRIEVAL,
        Stage.FACT_TOOLS,
        Stage.FACT_VALIDATION,
        Stage.GENERATION,
        Stage.GROUNDING,
        Stage.LANGUAGE_QUALITY,
        Stage.SAFETY_POST,
        Stage.PRESENCE,
        # §9's tail is "transcript store → memory-chip suggestion", in that
        # order: §6.4 gives a memory a source-message ref, so the chip needs a
        # message that already exists.
        Stage.PERSIST,
        Stage.MEMORY_CHIP,
    ]
    assert seen == [stage.value for stage in expected]


@pytest.mark.asyncio
async def test_the_transcript_carries_full_snapshots_not_references(pipeline_env) -> None:
    """§34.2: the artefact embeds the snapshot at generation time."""
    pipeline_env.llm.script("generate", GROUNDED)

    await run_turn(pipeline_env, "How's my work looking today?")

    user, assistant = pipeline_env.store.messages
    assert user["role"] == "user"
    assert assistant["fact_snapshots"][0]["fact_id"] == SATURN_FACT_ID
    assert assistant["fact_snapshots"][0]["value"]["whole_sign_house"] == 10
    # §6.4 / §33.1: the six audio fields are present on a text turn too.
    for audio_field in (
        "source_audio_asset_id",
        "tts_audio_asset_id",
        "transcript_status",
        "source_audio_expires_at",
        "source_audio_deleted_at",
        "playback_policy",
    ):
        assert audio_field in assistant


@pytest.mark.asyncio
async def test_a_guidance_log_backs_the_trust_sheet(pipeline_env) -> None:
    pipeline_env.llm.script("generate", GROUNDED)

    result = await run_turn(pipeline_env, "How's my work looking today?")

    (log,) = pipeline_env.store.guidance_logs
    assert log["confidence"] == ConfidenceState.VERIFIED.value
    assert log["fact_ids"] == [SATURN_FACT_ID]
    assert log["fact_snapshots"][0]["fact_id"] == SATURN_FACT_ID
    assert log["why"]["trace_id"] == result.trace_id


@pytest.mark.asyncio
async def test_an_l4_turn_never_reaches_the_model(pipeline_env) -> None:
    """§22.9: the crisis auto-response is instant and machine-delivered."""
    result = await run_turn(pipeline_env, "I don't want to live anymore")

    assert result.message_key == KEY_CRISIS
    assert result.review_queued
    assert result.presence_state is PresenceState.SAFETY_STILL
    assert result.fact_ids == ()
    assert [call.label for call in pipeline_env.llm.calls] == ["safety.l1"]
    entry = pipeline_env.review_queue.entries[0]
    assert entry.level is SafetyLevel.L4_CRISIS
    # The pseudonymised reference, never the user id (§6.4).
    assert entry.user_ref != USER_ID
    # §6.4's classifier_scores field gets actual scores, which is what §12's
    # pattern analytics reads.
    assert entry.assessment is not None
    assert entry.assessment.labels


@pytest.mark.asyncio
async def test_a_constrained_turn_asks_for_no_facts(pipeline_env) -> None:
    """§9: astrology framing removed at L2+, so no tool is called at all."""
    pipeline_env.llm.script("generate", "That sounds heavy. I'm here — tell me more.")

    result = await run_turn(pipeline_env, "Should I stop my medication?")

    assert result.safety.level is SafetyLevel.L3_REDIRECT
    assert result.intent is Intent.EMOTIONAL_SUPPORT
    assert result.presence_state is PresenceState.SAFETY_STILL
    assert pipeline_env.provider.calls == []
    assert result.fact_ids == ()


@pytest.mark.asyncio
async def test_missing_birth_data_asks_instead_of_guessing() -> None:
    """§5.3: missing data → Tara asks or declines, in-locale. No generation."""
    env = build_env()
    result = await run_turn(env, "What's happening in my chart?", profile=BirthProfile())

    assert result.message_key == KEY_MISSING_BIRTH_DATE
    assert result.confidence is ConfidenceState.CANNOT_CALCULATE
    assert "generate" not in [call.label for call in env.llm.calls]


@pytest.mark.asyncio
async def test_granted_tools_that_return_nothing_produce_a_decline() -> None:
    """An empty payload plus a chart question is the shape of a fabrication —
    so the turn declines rather than generating into the gap."""
    env = build_env(facts_by_tool={FactTool.TRANSITS: ()})

    result = await run_turn(env, "What's Saturn doing?")

    assert result.message_key == KEY_CANNOT_CALCULATE
    assert "generate" not in [call.label for call in env.llm.calls]


@pytest.mark.asyncio
async def test_small_talk_is_the_only_thing_that_gets_temperature_07() -> None:
    """§9: "Low-temperature (0.2) for guidance composition; 0.7 only for small
    talk." The pipeline declares it; the adapter applies what the model takes."""
    env = build_env()
    env.llm.script(
        "intent.route",
        {"intent": "greeting_smalltalk", "confidence": 0.95, "tools": [], "slots": {}},
    )
    env.llm.script("generate", "Good morning. How are you feeling today?")

    await run_turn(env, "morning Tara!")

    generate = next(call for call in env.llm.calls if call.label == "generate")
    assert generate.temperature == 0.7

    guidance = build_env()
    guidance.llm.script("generate", GROUNDED)
    await run_turn(guidance, "How's my work looking today?")
    assert next(c for c in guidance.llm.calls if c.label == "generate").temperature == 0.2


@pytest.mark.asyncio
async def test_the_persona_prefix_is_stable_across_turns(pipeline_env) -> None:
    """§9 caches the system prompt, which only works if it does not vary."""
    pipeline_env.llm.script("generate", GROUNDED, GROUNDED)

    await run_turn(pipeline_env, "How's my work looking today?")
    await run_turn(pipeline_env, "And tomorrow?")

    first, second = (c for c in pipeline_env.llm.calls if c.label == "generate")
    assert first.system == second.system


@pytest.mark.asyncio
async def test_the_trace_records_shapes_not_message_content(pipeline_env) -> None:
    """§13: message content can structurally never appear in logs."""
    pipeline_env.llm.script("generate", GROUNDED)
    secret = "How's my work looking today?"

    await run_turn(pipeline_env, secret)

    dumped = repr(pipeline_env.trace.events)
    assert secret not in dumped
    assert "Saturn is moving through" not in dumped
    generation = pipeline_env.trace.spans_for(Stage.GENERATION)[0]
    assert generation["metadata"]["content_sha256_16"]
    assert generation["usage"]["total"] == 150


@pytest.mark.asyncio
async def test_facts_are_gathered_only_for_granted_tools() -> None:
    env = build_env(
        facts_by_tool={
            FactTool.TRANSITS: (transit_house_fact(Graha.SATURN, 10, SATURN_FACT_ID),),
        }
    )
    env.llm.script("generate", GROUNDED)

    await run_turn(env, "How's my work looking today?")

    assert env.provider.calls == [FactTool.TRANSITS]


@pytest.mark.asyncio
async def test_a_fear_selling_reply_is_regenerated_then_replaced() -> None:
    """§9's post-check shares the one-regeneration rule with the other two."""
    env = build_env()
    env.llm.script(
        "generate",
        f"You will lose everything this month [[{SATURN_FACT_ID}]].",
        f"This is a month for careful spending [[{SATURN_FACT_ID}]].",
    )

    result = await run_turn(env, "How's money looking?")

    assert result.regenerations == 1
    assert not result.review_queued
    assert "lose everything" not in result.text
    assert [s["status"] for s in env.trace.spans_for(Stage.SAFETY_POST)] == ["failed", "passed"]
