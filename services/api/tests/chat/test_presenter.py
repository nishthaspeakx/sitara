"""§25.4's citation spans and §30.4's three layers, over the REAL pipeline.

The first of the two tests this milestone was specified around: **a fabricated
claim from the model must never reach the bubble.** It is written against the
real pipeline with a scripted model, because the guarantee is a property of the
pipeline and the presenter together — the validator rejecting a fabrication is
worth nothing if the presenter then renders the rejected draft.
"""

from __future__ import annotations

import pytest
from sitara_schemas.chat import SafetyLevel, SourceState
from sitara_schemas.facts import ConfidenceState, Graha

from sitara_api.chat_orchestration.pipeline import KEY_FALLBACK
from sitara_api.chat_orchestration.presenter import present_turn
from sitara_api.chat_orchestration.types import FactTool, PresenceState, TurnRequest
from tests.chat.conftest import (
    CONVERSATION_ID,
    NOW,
    SATURN_FACT_ID,
    USER_ID,
    VENUS_FACT_ID,
    build_env,
    transit_house_fact,
)

pytestmark = pytest.mark.asyncio

#: The sentence the model is scripted to produce when it behaves.
GROUNDED = (
    f"Saturn is moving through your 10th house today [[{SATURN_FACT_ID}]]. "
    "Take the slow route with work decisions."
)


def _request(text: str = "what is Saturn doing?", **kwargs: object) -> TurnRequest:
    return TurnRequest(
        user_id=USER_ID,
        conversation_id=CONVERSATION_ID,
        text=text,
        locale="en",
        now=NOW,
        **kwargs,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# T1 — a fabricated claim never reaches the bubble
# ---------------------------------------------------------------------------


async def test_a_fabricated_claim_never_reaches_the_bubble() -> None:
    """The model invents a transit. Both regenerations invent one.

    §9 allows exactly one corrective regeneration and then serves the safe
    fallback line. What this asserts is the part the presenter owns: the
    fabricated SENTENCE appears nowhere in the rendered turn — not in `text`,
    not inside a citation's Trust Sheet, not as a span the client could
    underline — and the turn says plainly that it stands on nothing.
    """
    env = build_env()
    fabrication = (
        "Jupiter is crossing your 7th house this week, so marriage talks will "
        f"go well [[{VENUS_FACT_ID}]]."
    )
    env.llm.script("generate", fabrication, fabrication)

    result = await env.pipeline.run(_request(profile=env.profile))
    turn = present_turn(result)

    rendered = " ".join(
        [turn.text, *(c.trust.plain for c in turn.citations)]
        + [line for c in turn.citations for line in c.trust.details]
    )
    assert "Jupiter" not in rendered
    assert "7th house" not in rendered
    assert "marriage" not in rendered

    # It fell back, and it says so rather than dressing the fallback as an answer.
    assert turn.message_key == KEY_FALLBACK
    assert turn.citations == ()
    assert turn.review_queued is True


async def test_the_fabricated_fact_id_never_reaches_the_client_either() -> None:
    """§30.4: fact-IDs "remain internal (logs/admin) and never render to users".

    A fabrication usually arrives WITH a citation — that is what makes it read
    like a real transit. The id must not travel even when the turn is rejected,
    and `ChatTurn` has no field it could travel in; this asserts the rendered
    JSON, which is what a reviewer would actually inspect.
    """
    env = build_env()
    invented_id = "fact:transit.jupiter.house:2026-08-08:deadbeef:1"
    reply = f"Jupiter sits in your 7th house [[{invented_id}]]."
    env.llm.script("generate", reply, reply)

    result = await env.pipeline.run(_request(profile=env.profile))
    body = present_turn(result).model_dump_json()

    assert invented_id not in body
    assert "fact:" not in body


async def test_a_rejected_turn_carries_no_spans_even_when_it_cited_correctly() -> None:
    """Grounding is not the only gate. A reply that cites perfectly and then
    fails the fear-selling lint (§9's safety post-check) is still discarded,
    and the citation spans must be discarded with it — otherwise the fallback
    line ships wearing the underlines of the sentence it replaced.
    """
    env = build_env()
    fear = (
        f"Saturn is in your 10th house [[{SATURN_FACT_ID}]]. "
        "Your marriage will end in ruin if you ignore this."
    )
    env.llm.script("generate", fear, fear)

    result = await env.pipeline.run(_request(profile=env.profile))
    turn = present_turn(result)

    assert turn.message_key == KEY_FALLBACK
    assert turn.citations == ()
    assert "ruin" not in turn.text


# ---------------------------------------------------------------------------
# The spans themselves
# ---------------------------------------------------------------------------


async def test_a_cited_sentence_becomes_a_span_over_the_served_text() -> None:
    """§25.4's underline, and the offsets it is drawn at.

    The assertion that matters is the SLICE: `text[span_start:span_end]` must
    be the claim. Any off-by-one in the marker-stripping or the whitespace
    normalisation shows up here as an underline starting mid-word.
    """
    env = build_env()
    env.llm.script("generate", GROUNDED)

    result = await env.pipeline.run(_request(profile=env.profile))
    turn = present_turn(result)

    assert len(turn.citations) == 1
    citation = turn.citations[0]
    assert turn.text[citation.span_start : citation.span_end] == (
        "Saturn is moving through your 10th house today"
    )
    # The uncited second sentence is NOT underlined — it makes no claim about
    # the day, so §30.4 has no sheet to put behind it.
    assert "slow route" not in turn.text[citation.span_start : citation.span_end]
    assert "[[" not in turn.text


async def test_the_span_carries_thirty_point_fours_three_layers() -> None:
    env = build_env()
    env.llm.script("generate", GROUNDED)

    result = await env.pipeline.run(_request(profile=env.profile))
    trust = present_turn(result).citations[0].trust

    # Layer 1 is the claim itself, in the words the reader tapped — as a
    # SENTENCE, terminal stop and all, because that is what a sheet shows. The
    # span is trimmed and this is not, and the difference is deliberate: an
    # underline runs under words, a quoted line is punctuated.
    assert trust.plain == "Saturn is moving through your 10th house today."
    # Layer 2 says how we know it.
    assert trust.sources_line
    assert trust.sources_line != trust.plain
    # Layer 3 reads the fact, rather than paraphrasing layer 1.
    assert trust.details
    assert all(line != trust.plain for line in trust.details)


async def test_the_span_never_carries_a_fact_id() -> None:
    """The component-side guarantee (`TrustSheet` has no prop for one) held to
    on the wire too. §28.2's payload has been held to this since M8."""
    env = build_env()
    env.llm.script("generate", GROUNDED)

    result = await env.pipeline.run(_request(profile=env.profile))
    body = present_turn(result).model_dump_json()

    assert SATURN_FACT_ID not in body


async def test_two_claims_get_two_spans_in_order() -> None:
    """Two sentences, two facts, two underlines — and the second span starts
    after the first ends. The scan is forward-only, so a repeated sentence
    cannot collapse both citations onto the first occurrence."""
    env = build_env(
        facts_by_tool={
            FactTool.TRANSITS: (
                transit_house_fact(Graha.SATURN, 10, SATURN_FACT_ID),
                transit_house_fact(Graha.VENUS, 5, VENUS_FACT_ID),
            )
        }
    )
    env.llm.script(
        "generate",
        f"Saturn is in your 10th house today [[{SATURN_FACT_ID}]]. "
        f"Venus is in your 5th house today [[{VENUS_FACT_ID}]].",
    )

    result = await env.pipeline.run(_request(profile=env.profile))
    turn = present_turn(result)

    assert len(turn.citations) == 2
    first, second = turn.citations
    assert first.span_end <= second.span_start
    assert turn.text[first.span_start : first.span_end].startswith("Saturn")
    assert turn.text[second.span_start : second.span_end].startswith("Venus")


async def test_the_confidence_on_a_span_is_the_weakest_fact_it_stands_on() -> None:
    """§5.4's rule, applied per claim rather than per turn. A bubble can hold a
    verified sentence beside a tradition-general one, and rounding either way
    is dishonest — the understating direction is the one nobody reports."""
    env = build_env()
    env.llm.script("generate", GROUNDED)

    result = await env.pipeline.run(_request(profile=env.profile))
    citation = present_turn(result).citations[0]

    assert citation.confidence is ConfidenceState.VERIFIED
    assert citation.source_state is SourceState.DEFAULT


# ---------------------------------------------------------------------------
# The rest of the turn
# ---------------------------------------------------------------------------


async def test_the_safety_level_crosses_the_wire_as_a_named_state() -> None:
    """§22.9/§29.1's "L3+ takes over the screen" needs the client to know which
    rung it is on. The ordinal comparison is DECLARED once in the schema
    (`SAFETY_TAKEOVER_FROM_ORDINAL`) rather than written as `>= 3` on each
    side."""
    env = build_env()
    env.llm.script("generate", GROUNDED)

    result = await env.pipeline.run(_request(profile=env.profile))
    turn = present_turn(result)

    assert turn.safety_level is SafetyLevel.L1_CLEAR
    assert turn.presence_state is PresenceState.CALM_GUIDANCE


async def test_an_l4_turn_presents_as_the_crisis_state() -> None:
    """§22.9: the L4 auto-response is templated, instant and never reaches the
    model. What the CLIENT must get is the rung and the safety-still presence,
    because that is what makes it take the screen over."""
    env = build_env()

    result = await env.pipeline.run(
        _request("I want to kill myself", profile=env.profile)
    )
    turn = present_turn(result)

    assert turn.safety_level is SafetyLevel.L4_CRISIS
    assert turn.presence_state is PresenceState.SAFETY_STILL
    assert turn.citations == ()
    assert turn.message_key
