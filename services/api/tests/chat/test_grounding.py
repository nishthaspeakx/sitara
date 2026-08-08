"""§5.3 step 9 / §9 — cite-or-die. A fabricated transit must never reach a user.

This test was written before the pipeline existed: it is the acceptance test
for the grounding validator and for §9's "fail → ONE corrective regeneration
→ fail → safe fallback line + human review queue" rule.

The LLM is scripted. Nothing here touches a network — the point is that the
validator, not the model's good behaviour, is what keeps a fabricated fact out
of a user's hands.
"""

import dataclasses

import pytest

from sitara_api.chat_orchestration.grounding import GroundingValidator, GroundingVerdict
from sitara_api.chat_orchestration.types import Stage
from tests.chat.conftest import SATURN_FACT_ID, VENUS_FACT_ID, run_turn

# The fact payload holds Saturn in the 10th. Nothing about Venus, nothing
# about the 7th house — every sentence below that claims otherwise is a
# fabrication the validator has to catch.
FABRICATED = (
    "Right now Venus is transiting your 7th house, so relationships feel warm today "
    f"[[{VENUS_FACT_ID}]]."
)
UNCITED = "Right now Saturn is transiting your 10th house, so work themes rise today."
GROUNDED = (
    "Right now Saturn is moving through your 10th house, "
    f"so work themes rise today [[{SATURN_FACT_ID}]]."
)
WRONG_NUMBER = f"Saturn is moving through your 4th house today [[{SATURN_FACT_ID}]]."


# --------------------------------------------------------------------------
# The validator in isolation
# --------------------------------------------------------------------------


def test_fabricated_transit_is_rejected(validator: GroundingValidator, saturn_facts) -> None:
    """The headline case: a cited fact-ID that is not in the served payload.

    The citation is well-formed and the sentence reads perfectly. Only
    membership in the payload distinguishes it from a real reading.
    """
    verdict = validator.check(FABRICATED, saturn_facts, locale="en")

    assert not verdict.ok
    assert "transit.venus.house" in " ".join(verdict.uncited_claims + verdict.unknown_fact_ids)
    assert VENUS_FACT_ID in verdict.unknown_fact_ids
    assert SATURN_FACT_ID not in verdict.cited_fact_ids


def test_uncited_astrological_claim_is_rejected(
    validator: GroundingValidator, saturn_facts
) -> None:
    """Right content, no citation. §5.3: every claim cites a fact-ID."""
    verdict = validator.check(UNCITED, saturn_facts, locale="en")

    assert not verdict.ok
    assert verdict.uncited_claims


def test_grounded_claim_passes(validator: GroundingValidator, saturn_facts) -> None:
    verdict = validator.check(GROUNDED, saturn_facts, locale="en")

    assert verdict.ok, verdict.reasons
    assert verdict.cited_fact_ids == (SATURN_FACT_ID,)
    # The user never sees the citation markers.
    assert "[[" not in verdict.clean_text
    assert verdict.clean_text.endswith("work themes rise today.")


def test_number_not_in_the_snapshot_is_rejected(
    validator: GroundingValidator, saturn_facts
) -> None:
    """§5.3 step 9: numbers match the facts verbatim. A real citation
    attached to a wrong number is still a fabrication."""
    verdict = validator.check(WRONG_NUMBER, saturn_facts, locale="en")

    assert not verdict.ok
    assert any("4" in reason for reason in verdict.reasons)


def test_non_astrological_sentences_need_no_citation(
    validator: GroundingValidator, saturn_facts
) -> None:
    """Warmth is not a claim. Only astrology-touching sentences are gated."""
    verdict = validator.check("Good morning — how are you feeling today?", saturn_facts, "en")

    assert verdict.ok, verdict.reasons


# --------------------------------------------------------------------------
# The same failure, through the whole pipeline
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_regenerates_once_after_a_fabricated_transit(pipeline_env) -> None:
    """First draft fabricates, the corrective regeneration is grounded.

    The user must receive the grounded second draft and never the first.
    """
    pipeline_env.llm.script("generate", FABRICATED, GROUNDED)

    result = await run_turn(pipeline_env, "What's Saturn doing for me today?")

    assert result.regenerations == 1
    assert not result.review_queued
    assert "Venus" not in result.text
    assert "7th house" not in result.text
    assert result.text.startswith("Right now Saturn is moving through your 10th house")
    assert result.fact_ids == (SATURN_FACT_ID,)
    # The snapshot travels with the artefact (§34.2), not just its id.
    assert [f.fact_id for f in result.fact_snapshots] == [SATURN_FACT_ID]

    grounding = pipeline_env.trace.spans_for(Stage.GROUNDING)
    assert [span["status"] for span in grounding] == ["failed", "passed"]


@pytest.mark.asyncio
async def test_pipeline_falls_back_when_the_regeneration_also_fabricates(pipeline_env) -> None:
    """§9: one corrective regeneration, then the safe fallback line and the
    human review queue. Never a second retry, never the fabricated text."""
    pipeline_env.llm.script("generate", FABRICATED, WRONG_NUMBER)

    result = await run_turn(pipeline_env, "What's Saturn doing for me today?")

    assert result.regenerations == 1
    assert result.review_queued
    assert result.message_key == "chat.fallback.safe_line"
    assert "Venus" not in result.text
    assert "4th house" not in result.text
    assert result.fact_ids == ()

    # Exactly two generation attempts — the ladder does not loop.
    assert len(pipeline_env.trace.spans_for(Stage.GENERATION)) == 2
    assert pipeline_env.review_queue.entries[0].stage is Stage.GROUNDING


@pytest.mark.asyncio
async def test_fabricated_text_is_never_persisted_as_a_message(pipeline_env) -> None:
    """A rejected draft is not a message. The transcript must not carry it —
    §34.2 artefacts are read back verbatim years later."""
    pipeline_env.llm.script("generate", FABRICATED, GROUNDED)

    await run_turn(pipeline_env, "What's Saturn doing for me today?")

    saved = [m for m in pipeline_env.store.messages if m["role"] == "assistant"]
    assert len(saved) == 1
    assert "Venus" not in saved[0]["content"]
    assert saved[0]["fact_ids"] == [SATURN_FACT_ID]


def test_verdict_is_frozen() -> None:
    """The verdict is evidence for the safety queue — it must not be edited
    after the fact by a later stage."""
    verdict = GroundingVerdict(ok=True, clean_text="hi")
    with pytest.raises(dataclasses.FrozenInstanceError):
        verdict.ok = False  # type: ignore[misc]
