"""`TurnResult` → §25.4's wire shape.

Pure over its inputs, like `daily_guidance/presenter.py` and for the same
reason: everything here is a rendering decision, and rendering decisions are the
ones worth being able to test without a database, a clock or a network.

**The citation spans are the whole point of this file.** §25.4 says
"fact-citation underlines ... render inside bubbles", and until now the client
could not have drawn one: `TurnResult.text` arrives already stripped of its
`[[fact:…]]` markers (§30.4 — the ids are internal), so the words that stand on
a fact were indistinguishable from the words that do not. The grounding
validator is the only thing in the pipeline that ever knew, because it decided
sentence by sentence; `GroundingVerdict.cited_sentences` records what it
decided, and this file turns that into offsets.

**A span is a sentence.** The marker sits inside the sentence before the final
stop (the rule `daily_guidance`'s composer follows), and the validator judges a
whole sentence at a time — so the sentence is the unit that was actually
verified. Underlining less would claim a precision nothing measured, and would
need the model to mark sub-spans, which nothing asks it to do.

**Fact IDs stop here**, exactly as they stop in the Today presenter. `ChatTurn`
has no field one could travel in and a parity test asserts the absence.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from sitara_schemas.chat import (
    ChatCitation,
    ChatTrust,
    ChatTurn,
    MemoryChipOffer,
    SafetyLevel,
    SourceState,
)
from sitara_schemas.facts import ConfidenceState, FactSnapshot

from sitara_api import text as textutil
from sitara_api import trust
from sitara_api.chat_orchestration.types import CitedSentence, TurnResult

logger = logging.getLogger(__name__)


def present_turn(result: TurnResult) -> ChatTurn:
    """One validated turn, as §25.4 and §30.4 need it rendered."""
    return ChatTurn(
        message_id=result.message_id or "",
        text=result.text,
        locale=result.locale,
        confidence=result.confidence,
        safety_level=SafetyLevel(result.safety.level.name.lower()),
        presence_state=result.presence_state,
        intent=result.intent.value,
        trace_id=result.trace_id,
        citations=present_citations(
            result.text,
            result.cited_sentences,
            result.fact_snapshots,
            result.locale,
            fallback=result.confidence,
        ),
        memory_chips=tuple(
            MemoryChipOffer(
                type=chip.type,
                summary=chip.content,
                requires_reconfirmation=chip.requires_reconfirmation,
            )
            for chip in result.memory_chips
        ),
        review_queued=result.review_queued,
        message_key=result.message_key,
        budget_notice_key=result.budget_notice_key,
    )


def present_citations(
    text: str,
    cited: Sequence[CitedSentence],
    snapshots: Sequence[FactSnapshot],
    locale: str,
    *,
    fallback: ConfidenceState,
) -> tuple[ChatCitation, ...]:
    """Locate each verified sentence in the served text and render its sheet.

    The offsets are found rather than tracked, because `strip_citations` also
    normalises whitespace: an index taken before the markers are removed does
    not survive the removal. So each sentence is cleaned the same way and
    located in the cleaned whole, scanning forward — which is exact for the
    text the composer and the model actually produce, and never guesses.

    A sentence that cannot be located is DROPPED and logged loudly, because
    §30.4 requires every astrological claim to reach a Trust Sheet in one tap
    and a citation that silently fails to render is a claim that does not. The
    ConfidenceChip still renders on the bubble either way, so the turn stays
    honest about its evidence even in the case this cannot draw.

    Offsets are in Unicode code points. Python strings are code points already;
    the client converts, and `ChatCitation`'s comment says which — Devanagari
    and emoji both make code points and UTF-16 units differ, and an underline
    off by two characters in Hindi is the kind of bug that reads as a font
    problem for a week.
    """
    by_id = {s.fact_id: s for s in snapshots}
    citations: list[ChatCitation] = []
    cursor = 0

    for sentence in cited:
        start = text.find(sentence.text, cursor)
        if start < 0:
            # Not a crash: the turn is still true and still shows its
            # confidence. But it IS a defect in this function, so it must be
            # findable rather than absorbed.
            logger.warning(
                "cited sentence not locatable in the served text — no underline rendered",
                extra={"locale": locale, "length": len(sentence.text)},
            )
            continue
        end = start + len(sentence.text)
        cursor = end
        # The underline sits under the CLAIM, not under its full stop. The
        # sentence splitter keeps the ender (it splits on the whitespace after
        # one), and an underline that runs through the punctuation reads as a
        # rendering bug in every locale — the danda especially.
        end = _without_terminator(text, start, end)

        supporting = [by_id[fid] for fid in sentence.fact_ids if fid in by_id]
        state = trust.weakest(supporting, fallback)
        layers = trust.layers(supporting, state, locale, text=sentence.text)
        citations.append(
            ChatCitation(
                span_start=start,
                span_end=end,
                confidence=state,
                source_state=_source_state(state),
                trust=ChatTrust(
                    plain=layers.plain,
                    sources_line=layers.sources_line,
                    details=layers.details,
                ),
            )
        )

    return tuple(citations)


def _without_terminator(text: str, start: int, end: int) -> int:
    """Shrink `end` back over trailing sentence enders and whitespace."""
    while end > start and text[end - 1] in textutil.SENTENCE_END + " \t\n":
        end -= 1
    return end


def _source_state(state: ConfidenceState) -> SourceState:
    """§34.7's VerifiedSourceRow state, from §5.4's confidence state.

    The same derivation `trust.sources_line` makes, so the row's glyph and its
    sentence cannot disagree. `disputed` is unreachable from here on purpose: a
    disputed fact is downgraded and queued for adjudication upstream (§32.2),
    so it never reaches a rendered claim wearing its own label. The state
    exists in the component because the ADMIN comparison surface shows it.
    """
    return (
        SourceState.DEFAULT if state is ConfidenceState.VERIFIED else SourceState.SINGLE
    )
