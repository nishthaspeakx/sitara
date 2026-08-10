"""GENERATED FILE — do not edit. Source: packages/schemas/src/*.json (run scripts/generate.py).

SPEC §25.4 / §30.4 — one chat turn, as it crosses the wire.

Served identically by `POST /v1/chat/turn` and by the §34.6 socket's
`captions.final`, because a turn that renders one way over HTTP and
another over the socket is two chat screens wearing one name.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from sitara_schemas.facts import ConfidenceState
from sitara_schemas.memory_types import MemoryType
from sitara_schemas.presence import PresenceState

__all__ = [
    "CITATION_SPANS_ARE_SENTENCES",
    "ChatCitation",
    "ChatRole",
    "ChatTrust",
    "ChatTurn",
    "MemoryChipOffer",
    "SAFETY_LEVEL_ORDINAL",
    "SAFETY_TAKEOVER_FROM_ORDINAL",
    "SafetyLevel",
    "SourceState",
]


class ChatRole(StrEnum):
    """§25.4's two authors. There is no third — group mechanics are deliberately dropped from the WhatsApp grammar, so there is no shape here that could carry a third party."""

    USER = "user"
    TARA = "tara"


class SafetyLevel(StrEnum):
    """§9's L1–L5 ladder, as the client must see it. §22.9 and §29.1: L3+ takes the screen over. The threshold is DECLARED below rather than written as `>= 3` on each side."""

    L1_CLEAR = "l1_clear"
    L2_CONSTRAINED = "l2_constrained"
    L3_REDIRECT = "l3_redirect"
    L4_CRISIS = "l4_crisis"
    L5_HUMAN_REVIEW = "l5_human_review"


class SourceState(StrEnum):
    """§34.7's three VerifiedSourceRow states. Served, never inferred client-side: whether two almanacs corroborated a fact is something only §32.2's adjudication knows."""

    DEFAULT = "default"
    SINGLE = "single"
    DISPUTED = "disputed"


#: §9's ladder as numbers, for the ONE comparison the client and the
#: server both make: is this L3 or above?
SAFETY_LEVEL_ORDINAL: dict[SafetyLevel, int] = {
    SafetyLevel.L1_CLEAR: 1,
    SafetyLevel.L2_CONSTRAINED: 2,
    SafetyLevel.L3_REDIRECT: 3,
    SafetyLevel.L4_CRISIS: 4,
    SafetyLevel.L5_HUMAN_REVIEW: 5,
}


#: §22.9 / §29.1 — 'safety takeover (/support/now, L3+)'. One number, read by the server when it decides and by the client when it renders, so the two can never disagree about what L3+ means.
SAFETY_TAKEOVER_FROM_ORDINAL = 3

#: §30.4 — the citation marker sits INSIDE the sentence, before the final stop (the rule daily-guidance's composer already follows), and the grounding validator judges a sentence at a time. So the underlined span is the sentence, which is the unit that was actually verified. A narrower span would claim a precision nothing measured.
CITATION_SPANS_ARE_SENTENCES = 1


class ChatTrust(BaseModel):
    """§30.4's three layers, already rendered — the same shape and the same reason as TodayTrust. Fact IDs are absent BY SHAPE: there is no field one could travel in, which is the guarantee TrustSheet's props already give on the component side."""

    model_config = ConfigDict(frozen=True)

    plain: str
    sources_line: str
    details: tuple[str, ...]


class ChatCitation(BaseModel):
    """§25.4's fact-citation underline. `span_start`/`span_end` index into the turn's `text` (Unicode code points, not UTF-16 units — Devanagari and emoji both make those differ). One citation per verified sentence."""

    model_config = ConfigDict(frozen=True)

    span_start: int
    span_end: int
    confidence: ConfidenceState
    source_state: SourceState
    trust: ChatTrust


class MemoryChipOffer(BaseModel):
    """§32.4 — a SUGGESTION. Nothing is stored without the explicit chip, so this shape carries no memory id: there is no memory yet. `requires_reconfirmation` is types 7–9's 'always re-confirm wording before save'."""

    model_config = ConfigDict(frozen=True)

    type: MemoryType
    summary: str
    requires_reconfirmation: bool


class ChatTurn(BaseModel):
    """One of Tara's turns, after every §9 validator has passed. There is no shape for an unvalidated one, anywhere, in either language — which is what makes 'a fabricated claim never reaches a bubble' a property of the contract rather than a rule someone has to keep."""

    model_config = ConfigDict(frozen=True)

    message_id: str
    text: str
    locale: str
    confidence: ConfidenceState
    safety_level: SafetyLevel
    presence_state: PresenceState
    intent: str
    trace_id: str
    citations: tuple[ChatCitation, ...]
    memory_chips: tuple[MemoryChipOffer, ...]
    review_queued: bool
    message_key: str | None = None
    budget_notice_key: str | None = None
