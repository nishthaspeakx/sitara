"""GENERATED FILE — do not edit. Source: packages/schemas/src/*.json (run scripts/generate.py)."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict


class ControlEventType(StrEnum):
    """SPEC §34.6 — the CLOSED control-event type set for the voice/call WS protocol."""

    SESSION_START = "session.start"
    SESSION_READY = "session.ready"
    SESSION_END = "session.end"
    VAD_STATE = "vad.state"
    BARGE_IN = "barge_in"
    TTS_START = "tts.start"
    TTS_CHUNK_META = "tts.chunk_meta"
    TTS_END = "tts.end"
    PRESENCE_STATE = "presence.state"
    CAPTIONS_PARTIAL = "captions.partial"
    CAPTIONS_FINAL = "captions.final"
    ENTITLEMENT_WARNING = "entitlement.warning"
    ERROR = "error"
    HANDOFF_TO_TEXT = "handoff.to_text"
    RESUME_OFFER = "resume.offer"


class ControlEvent(BaseModel):
    """SPEC §34.6 — JSON text-frame control event {type, seq, ts, payload}."""

    model_config = ConfigDict(frozen=True)

    type: ControlEventType
    seq: int
    ts: float
    payload: dict[str, Any]


# Binary frame contract (SPEC §34.6): 16kHz mono PCM, 8-byte header.
BINARY_AUDIO_FORMAT = "pcm_s16le"
BINARY_SAMPLE_RATE_HZ = 16000
BINARY_CHANNELS = 1
BINARY_HEADER_BYTES = 8
BINARY_HEADER_SEQ_BYTES = 4
BINARY_HEADER_FLAGS_BYTES = 4

HEARTBEAT_INTERVAL_S = 10
REAP_AFTER_SILENCE_S = 30
RESUME_WINDOW_S = 300
