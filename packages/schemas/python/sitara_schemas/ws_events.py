"""GENERATED FILE — do not edit. Source: packages/schemas/src/*.json (run scripts/generate.py)."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict

from sitara_schemas.chat import ChatRole, ChatTurn
from sitara_schemas.presence import PresenceState


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
    """SPEC §34.6 — JSON text-frame control event {type, seq, ts, ack, payload}."""

    model_config = ConfigDict(frozen=True)

    type: ControlEventType
    seq: int
    ts: float
    ack: int | None = None
    payload: dict[str, Any]


# --------------------------------------------------------------------
# Payload shapes — the TEXT-chat subset only.
#
# §34.6 says payloads are 'typed per event in M9'. The members the text
# chat uses are typed HERE, one milestone early, because S18 sends them
# now; the voice members (vad.state, barge_in, tts.*, entitlement.warning)
# stay untyped until M9 builds the thing that emits them. Typing an event
# nobody produces yet would be a guess with a schema around it.
# --------------------------------------------------------------------

class SessionStartPayload(BaseModel):
    """Client → server. The ticket is single-use and 60-second; §34.5's session cookies are httpOnly and first-party, and a WebSocket handshake to another origin does not carry them."""

    model_config = ConfigDict(frozen=True)

    ticket: str
    conversation_id: str
    locale: str
    resume_token: str | None = None


class SessionReadyPayload(BaseModel):
    """Server → client. `resume_token` is what a reconnect inside `resume_window_s` presents (§32.11)."""

    model_config = ConfigDict(frozen=True)

    resume_token: str
    resume_window_s: int
    conversation_id: str


class UserTurnPayload(BaseModel):
    """Client → server, on `captions.final`. Discriminated from the Tara direction by `role`."""

    model_config = ConfigDict(frozen=True)

    role: ChatRole
    text: str
    client_message_id: str
    quoted_message_id: str | None = None


class TaraTurnPayload(BaseModel):
    """Server → client, on `captions.final`. Carries the whole validated turn and nothing else — there is no field here for text that has not been through §9's validators."""

    model_config = ConfigDict(frozen=True)

    role: ChatRole
    client_message_id: str
    turn: ChatTurn


class PresenceStatePayload(BaseModel):
    """Server → client. The client switches on `state` alone. `stage` is §9's pipeline step, carried for traces and analytics — a shape, not content (§13) — and deliberately not something the UI branches on: the presence state is the designed vocabulary (§4.3) and the stage list is an implementation detail that may grow."""

    model_config = ConfigDict(frozen=True)

    state: PresenceState
    stage: str | None = None


class HandoffToTextPayload(BaseModel):
    """Server → client. `reason` is why the socket gave up, so the thread can say something true rather than 'something went wrong'."""

    model_config = ConfigDict(frozen=True)

    conversation_id: str
    reason: str


class ResumeOfferPayload(BaseModel):
    """Server → client (§32.11). `pending_turn` is the turn that COMPLETED while the socket was down — buffered rather than re-run, because re-running a turn charges a user twice for one question."""

    model_config = ConfigDict(frozen=True)

    conversation_id: str
    pending_turn: ChatTurn | None = None
    pending_client_message_id: str | None = None


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
