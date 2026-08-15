"""GENERATED FILE — do not edit. Source: packages/schemas/src/*.json (run scripts/generate.py).

SPEC §25.3 / §25.7 — the internal media socket between `sitara-realtime`
and `sitara-api`. Declared here because BOTH sides name the set, which is
this package's rule; see the source JSON for why it is not §34.6.
"""

from enum import StrEnum

__all__ = [
    "CALL_DOWN_FRAMES",
    "CALL_TICK_INTERVAL_S",
    "CALL_UP_FRAMES",
    "CallDownFrame",
    "CallUpFrame",
]


class CallUpFrame(StrEnum):
    """`sitara-realtime` → `sitara-api`. Realtime owns the §34.6 protocol, the server-side VAD and the session clock; everything it sends here is one of those three speaking."""

    UTTERANCE = "utterance"
    CANCEL_SPEECH = "cancel_speech"
    TICK = "tick"
    METRIC = "metric"
    END = "end"


CALL_UP_FRAMES: tuple[CallUpFrame, ...] = (
    CallUpFrame.UTTERANCE,
    CallUpFrame.CANCEL_SPEECH,
    CallUpFrame.TICK,
    CallUpFrame.METRIC,
    CallUpFrame.END,
)


class CallDownFrame(StrEnum):
    """`sitara-api` → `sitara-realtime`. Vendors, validators and the quota all live on this side."""

    CAPTION = "caption"
    STAGE = "stage"
    TURN = "turn"
    TTS_START = "tts_start"
    TTS_END = "tts_end"
    TTS_CANCELLED = "tts_cancelled"
    ENTITLEMENT_WARNING = "entitlement_warning"
    EXHAUSTED = "exhausted"
    ERROR = "error"


CALL_DOWN_FRAMES: tuple[CallDownFrame, ...] = (
    CallDownFrame.CAPTION,
    CallDownFrame.STAGE,
    CallDownFrame.TURN,
    CallDownFrame.TTS_START,
    CallDownFrame.TTS_END,
    CallDownFrame.TTS_CANCELLED,
    CallDownFrame.ENTITLEMENT_WARNING,
    CallDownFrame.EXHAUSTED,
    CallDownFrame.ERROR,
)


#: How often realtime reports elapsed seconds for metering. Ten seconds, matching §34.6's heartbeat, so a call carries one periodic obligation rather than two drifting ones. It bounds how late a §32.9 warning can be — never how EARLY the pool can run out, because `exhausted` is evaluated on the same tick.
CALL_TICK_INTERVAL_S = 10
