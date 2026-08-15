"""Shared contracts for the §9 chat-orchestration pipeline.

Every enum here is a closed set. The pipeline is a fixed sequence of stages
(§9's "mandatory pipeline (every turn)"), and `Stage` is that sequence spelled
out so a trace, a review-queue entry and a test can all name the same step.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum

from sitara_schemas.facts import ConfidenceState, FactSnapshot


class Stage(StrEnum):
    """§9's mandatory per-turn pipeline, in order.

    TTS render and the transcript-store→memory-chip tail of §9 sit after
    SAFETY_POST; PERSIST and MEMORY_CHIP are those steps. TTS_RENDER is
    declared so the voice module (M6) slots in without renumbering a trace.
    """

    LANGUAGE_DETECT = "language_detect"
    SAFETY_PRE = "safety_pre"
    INTENT = "intent"
    REQUIRED_DATA = "required_data"
    MEMORY_RETRIEVAL = "memory_retrieval"
    FACT_TOOLS = "fact_tools"
    FACT_VALIDATION = "fact_validation"
    GENERATION = "generation"
    GROUNDING = "grounding"
    LANGUAGE_QUALITY = "language_quality"
    SAFETY_POST = "safety_post"
    TTS_RENDER = "tts_render"
    PRESENCE = "presence"
    PERSIST = "persist"
    MEMORY_CHIP = "memory_chip"


# --------------------------------------------------------------------------
# Language (§2.4)
# --------------------------------------------------------------------------

#: The launch three. A locale outside this set is never guessed at (§2.4).
LAUNCH_LOCALES: tuple[str, ...] = ("en", "hi", "hi-Latn")


class Script(StrEnum):
    LATIN = "latin"
    DEVANAGARI = "devanagari"
    MIXED = "mixed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class DetectedLanguage:
    """What the user wrote in, and what we will answer in.

    `locale` is the answering locale: the user's chosen locale unless the
    turn itself is unambiguously in another launch locale. `matches_profile`
    is False when those differ, which the language-quality validator uses to
    check we did not silently drift (§2.4 — no silent fallback, ever).
    """

    locale: str
    script: Script
    detected_locale: str
    matches_profile: bool
    confidence: float


# --------------------------------------------------------------------------
# Safety (§9, §13, diagram 13)
# --------------------------------------------------------------------------


class SafetyLevel(IntEnum):
    """The v1 ladder carried forward (§9). Astrology framing is REMOVED at L2+."""

    L1_CLEAR = 1
    L2_CONSTRAINED = 2
    L3_REDIRECT = 3
    L4_CRISIS = 4
    L5_HUMAN_REVIEW = 5


class RiskClass(StrEnum):
    """L1 classifier categories (§9) plus the two routing classes the L2→L3
    branch of diagram 13 needs."""

    NONE = "none"
    SELF_HARM = "self_harm"
    MEDICAL = "medical"
    LEGAL = "legal"
    FINANCIAL_RISK = "financial_risk"
    MINORS = "minors"
    ABUSE = "abuse"
    EMOTIONAL_DISTRESS = "emotional_distress"
    ACUTE_CRISIS = "acute_crisis"


#: Risk classes that route to a professional redirect rather than support.
PROFESSIONAL_REDIRECT: frozenset[RiskClass] = frozenset(
    {RiskClass.MEDICAL, RiskClass.LEGAL, RiskClass.FINANCIAL_RISK}
)


@dataclass(frozen=True)
class SafetyLabel:
    """One scored category. Stored on the message (§6.4 `safety_labels`)."""

    risk_class: RiskClass
    score: float
    source: str  # "rules" | "classifier"


@dataclass(frozen=True)
class SafetyAssessment:
    level: SafetyLevel
    risk_class: RiskClass
    labels: tuple[SafetyLabel, ...] = ()
    #: True when the LLM classifier was unavailable and only rules ran. The
    #: turn still proceeds — rules alone can raise L4 — but it is recorded.
    degraded: bool = False

    @property
    def astrology_allowed(self) -> bool:
        """§9: astrology framing is removed at L2 and above."""
        return self.level is SafetyLevel.L1_CLEAR


# --------------------------------------------------------------------------
# Intent + the per-intent tool allowlist (§22.8)
# --------------------------------------------------------------------------


class Intent(StrEnum):
    """Closed routing set. The router emits ONLY these (structured output, §9)."""

    GREETING_SMALLTALK = "greeting_smalltalk"
    DAILY_GUIDANCE = "daily_guidance"
    TIMING_QUESTION = "timing_question"
    PANCHANG_LOOKUP = "panchang_lookup"
    NATAL_CHART_QUESTION = "natal_chart_question"
    NUMEROLOGY_QUESTION = "numerology_question"
    RELATIONSHIP_QUESTION = "relationship_question"
    FAMILY_MEMBER_QUESTION = "family_member_question"
    MEMORY_MANAGEMENT = "memory_management"
    ACCOUNT_OR_BILLING = "account_or_billing"
    EMOTIONAL_SUPPORT = "emotional_support"
    OUT_OF_SCOPE = "out_of_scope"
    UNCLEAR = "unclear"


class FactTool(StrEnum):
    """The astrology/numerology tools the LLM may REQUEST (never compute, §9)."""

    PANCHANG_DAY = "panchang_day"
    PANCHANG_DAY_TIMINGS = "panchang_day_timings"
    MUHURAT_WINDOW = "muhurat_window"
    NUMEROLOGY_PROFILE = "numerology_profile"
    NATAL_CHART = "natal_chart"
    TRANSITS = "transits"


#: §22.8 tool-call allowlist per intent — "a casual-chat turn cannot invoke
#: billing tools". Absent from the map means: no fact tools at all.
TOOL_ALLOWLIST: dict[Intent, frozenset[FactTool]] = {
    Intent.DAILY_GUIDANCE: frozenset(
        {
            FactTool.PANCHANG_DAY,
            FactTool.PANCHANG_DAY_TIMINGS,
            FactTool.TRANSITS,
            FactTool.NUMEROLOGY_PROFILE,
        }
    ),
    Intent.TIMING_QUESTION: frozenset(
        {FactTool.PANCHANG_DAY_TIMINGS, FactTool.MUHURAT_WINDOW, FactTool.PANCHANG_DAY}
    ),
    Intent.PANCHANG_LOOKUP: frozenset({FactTool.PANCHANG_DAY, FactTool.PANCHANG_DAY_TIMINGS}),
    Intent.NATAL_CHART_QUESTION: frozenset({FactTool.NATAL_CHART, FactTool.TRANSITS}),
    Intent.NUMEROLOGY_QUESTION: frozenset({FactTool.NUMEROLOGY_PROFILE}),
    Intent.RELATIONSHIP_QUESTION: frozenset({FactTool.NATAL_CHART, FactTool.TRANSITS}),
    Intent.FAMILY_MEMBER_QUESTION: frozenset({FactTool.NATAL_CHART}),
}

#: Intents that need no chart at all — §5.4's "tradition-based general" row.
CHARTLESS_INTENTS: frozenset[Intent] = frozenset(
    {
        Intent.GREETING_SMALLTALK,
        Intent.PANCHANG_LOOKUP,
        Intent.MEMORY_MANAGEMENT,
        Intent.ACCOUNT_OR_BILLING,
        Intent.EMOTIONAL_SUPPORT,
        Intent.OUT_OF_SCOPE,
        Intent.UNCLEAR,
    }
)

#: Small talk is the ONLY thing §9 permits temperature 0.7 for.
SMALL_TALK_INTENTS: frozenset[Intent] = frozenset({Intent.GREETING_SMALLTALK})


@dataclass(frozen=True)
class IntentDecision:
    intent: Intent
    confidence: float
    tools: tuple[FactTool, ...]
    #: Free-text slot the router filled (a city, a date) — never a computed value.
    slots: dict[str, str] = field(default_factory=dict)


# --------------------------------------------------------------------------
# Required data / confidence (§5.3 steps 2–3, §5.4)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class BirthProfile:
    """What we hold about the subject. Never a computed chart value."""

    has_date: bool = False
    has_exact_time: bool = False
    has_time_window: bool = False
    has_place: bool = False
    tz: str | None = None
    chart_version: int = 1


@dataclass(frozen=True)
class DataSufficiency:
    confidence: ConfidenceState
    #: Fields the turn needs and does not have — Tara asks for these in-locale.
    missing: tuple[str, ...] = ()

    @property
    def can_answer(self) -> bool:
        return self.confidence is not ConfidenceState.CANNOT_CALCULATE


# --------------------------------------------------------------------------
# Facts (§34.2)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidatedFacts:
    """Only validated fact-IDs reach interpretation (§5.3 step 7)."""

    snapshots: tuple[FactSnapshot, ...] = ()
    rejected: tuple[str, ...] = ()
    disputed: bool = False
    notes: tuple[str, ...] = ()

    @property
    def fact_ids(self) -> tuple[str, ...]:
        return tuple(f.fact_id for f in self.snapshots)

    def by_id(self, fact_id: str) -> FactSnapshot | None:
        return next((f for f in self.snapshots if f.fact_id == fact_id), None)


@dataclass(frozen=True)
class CitedSentence:
    """One sentence that carried a citation the served payload could honour.

    §25.4 puts a fact-citation underline inside the bubble, and the validator
    is the only thing in the pipeline that knows WHICH words stand on a fact —
    it decided sentence by sentence, and then `strip_citations` erased the
    evidence. Recording it here is cheaper and far more honest than a second
    pass over the text guessing where the markers used to be.

    The `text` is the sentence without its markers, terminal stop included —
    `text.sentences` splits on the whitespace AFTER an ender, so the ender
    rides along. The presenter trims it back off the span: §25.4's underline
    should sit under the claim, not under its full stop.
    """

    text: str
    fact_ids: tuple[str, ...]


# --------------------------------------------------------------------------
# Memory (§32.4, §32.5)
# --------------------------------------------------------------------------


# The taxonomy and its gates belong to the memory module (§6.3), which owns
# them. Re-exported here so P6a's call sites keep working — two copies of an
# 11-member closed set is how a twelfth member appears.
from sitara_api.memory import taxonomy as _taxonomy  # noqa: E402

MemoryType = _taxonomy.MemoryType
#: §32.4: types 7–9 are retrieved only in matching conversational context.
CONTEXT_GATED_MEMORY = _taxonomy.CONTEXT_GATED
#: §32.4: type 8 never surfaces in a celebratory or casual turn.
NEVER_IN_CASUAL = _taxonomy.NEVER_IN_CASUAL
#: §32.4: type 11 is always available.
ALWAYS_AVAILABLE_MEMORY = _taxonomy.ALWAYS_AVAILABLE


@dataclass(frozen=True)
class MemoryItem:
    memory_id: str
    type: MemoryType
    content: str
    score: float = 0.0


@dataclass(frozen=True)
class MemoryChip:
    """A SUGGESTION. Nothing is stored without the user's explicit chip (§32.4)."""

    type: MemoryType
    content: str
    #: Types 7–9 always re-confirm wording before save (§32.4).
    requires_reconfirmation: bool = False


# --------------------------------------------------------------------------
# Presence (§4.3) — the pipeline emits the tag, the client renders the asset
# --------------------------------------------------------------------------


# §4.3's twelve moved to `packages/schemas` in M8-P10, for the reason every
# closed set eventually moves there: the client needed to render one. It was an
# IntEnum here and a differently-named, differently-ORDERED list of twelve in
# `apps/web`, so a positional read resolved this module's SAFETY_STILL (11) —
# the state §29.5 puts in the chat header at L2+ — to the client's `reading`.
#
# It is a StrEnum now. §4.3's numbering survives in the schema package as
# `PRESENCE_ORDINAL`, for reading a list against the spec line; the ID is what
# crosses the wire and what a trace records, because a positional contract is
# exactly what drifted here.
from sitara_schemas.presence import PresenceState  # noqa: E402, I001


# --------------------------------------------------------------------------
# Turn in / turn out
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class TurnRequest:
    user_id: str
    conversation_id: str
    text: str
    #: The user's chosen locale (§2.4). Never inferred from a phone number.
    locale: str
    now: dt.datetime
    profile: BirthProfile = field(default_factory=BirthProfile)
    place_label: str | None = None
    history: tuple[dict[str, str], ...] = ()
    #: §25.4's swipe-to-reply: "the pipeline receives the quoted turn
    #: explicitly". Explicitly is the load-bearing word — a quote that only
    #: rendered in the bubble would give the user the feature's appearance and
    #: the model none of its context, so the reply would answer the wrong turn
    #: while the screen showed which turn it was supposed to be answering.
    quoted_message_id: str | None = None
    #: Rolling summary of everything older than `history` (§9 token budget).
    summary: str | None = None
    tokens_used_today: int = 0
    #: M9-P10b (§25.3). Set when the user's turn is ALREADY on the record — the
    #: pipeline then answers it and does not write it a second time.
    #:
    #: This exists because a call cannot be re-asked. `_persist` writes both
    #: messages at the END of the turn, so a pipeline that dies mid-turn loses
    #: the user's words along with the answer. A typed question survives that:
    #: it is still in the composer, and the client resends. **Spoken words do
    #: not.** Call audio is never stored (§13, §33.1), so the transcript is the
    #: only record there will ever be, and a provider outage between "she heard
    #: you" and "she answered" would erase what somebody said out loud.
    #:
    #: So the call service commits the transcript the moment STT finalises it
    #: and passes the id here. Same ordering discipline as §28.3's
    #: store-the-original-before-STT, one layer up: write the thing that cannot
    #: be recreated before the thing that can fail.
    user_message_id: str | None = None


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_read_tokens + other.cache_read_tokens,
            self.cache_write_tokens + other.cache_write_tokens,
        )


@dataclass(frozen=True)
class TurnResult:
    """What the caller renders. `text` is already in-locale and citation-free.

    `message_key` is set instead of a model-authored `text` whenever the turn
    was answered by a template: an L3/L4 safety response, a data request, or
    the safe fallback line. Those are never generated (§9, §22.9).
    """

    text: str
    locale: str
    confidence: ConfidenceState
    safety: SafetyAssessment
    intent: Intent
    presence_state: PresenceState
    trace_id: str
    fact_ids: tuple[str, ...] = ()
    fact_snapshots: tuple[FactSnapshot, ...] = ()
    memory_chips: tuple[MemoryChip, ...] = ()
    #: §25.4's fact-citation underlines, as the grounding validator saw them —
    #: one entry per claim-bearing sentence a served fact backed. Empty on any
    #: turn that was templated, declined or fell back: those stand on no fact.
    #: `chat_orchestration.presenter` turns these into offsets into `text`.
    cited_sentences: tuple[CitedSentence, ...] = ()
    message_key: str | None = None
    regenerations: int = 0
    review_queued: bool = False
    #: Set when the §9 per-user daily soft cap is crossed — a notice, not a block.
    budget_notice_key: str | None = None
    usage: TokenUsage = field(default_factory=TokenUsage)
    message_id: str | None = None
