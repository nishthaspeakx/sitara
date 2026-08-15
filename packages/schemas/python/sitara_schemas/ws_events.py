"""GENERATED FILE — do not edit. Source: packages/schemas/src/*.json (run scripts/generate.py)."""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from sitara_schemas.chat import ChatRole, ChatTurn
from sitara_schemas.presence import PresenceState
from sitara_schemas.voice import (
    BargeInReason,
    PlaybackPolicy,
    TranscriptStatus,
    VadState,
)


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
# Payload shapes — the text chat (S18), the voice notes (M9), the live
# call (M9-P10b). All fifteen members are now typed.
#
# §34.6 says payloads are 'typed per event in M9'. The rule that actually
# held is narrower: a payload is typed by the milestone that starts
# EMITTING it, because typing an event nobody produces is a guess with a
# schema around it. S18 typed the text-chat members, M9 typed vad.state
# and tts.*, and M9-P10b types the last two — `barge_in` (§25.3's server-side
# VAD ducking) and `entitlement.warning` (§7.3's minute pool) — because
# M9-P10b is the milestone that sends them.
#
# The set of MEMBERS has not moved and must not: fifteen, closed, §31.3
# change control. A live call speaking the same fifteen as a typed chat
# is what §34.6 claimed and what M9-P10b is the test of.
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
    """Client → server on `captions.final` when typed; server → client on the same member when the turn was SPOKEN and STT has finalised it. One shape for both because §34.6's whole premise is that a typed message and a transcribed one are the same event — the difference is which of the three §33.1 fields below are populated, not which member carries it. On a typed message they are `not_applicable` / `text_only` / null, which is exactly what the store already writes."""

    model_config = ConfigDict(frozen=True)

    role: ChatRole
    text: str
    client_message_id: str
    quoted_message_id: str | None = None
    transcript_status: TranscriptStatus
    playback_policy: PlaybackPolicy
    source_audio_asset_id: str | None = None
    duration_ms: int | None = None
    source_audio_expires_at: str | None = None


class PartialCaptionPayload(BaseModel):
    """Server → client, on `captions.partial`. `role` is the CONSTANT "user" and not a ChatRole, which is the whole point of the shape: §9 runs grounding, language-quality and safety-post after generation, so a partial caption of TARA's words would be pre-validation text racing three validators to the screen. Through M8 that was guaranteed by nobody writing the frame. Now the frame exists, for the user's own speech, and the guarantee is that there is no value of `role` here that could carry hers."""

    model_config = ConfigDict(frozen=True)

    role: Literal["user"]
    text: str
    client_message_id: str


class VadStatePayload(BaseModel):
    """Client → server, on `vad.state`. Brackets a held recording. `client_message_id` is minted before the first PCM byte leaves, so every binary frame in the bracket already belongs to a bubble the thread is drawing — the transcript lands in a message that exists rather than appearing from nowhere when STT returns."""

    model_config = ConfigDict(frozen=True)

    state: VadState
    client_message_id: str
    quoted_message_id: str | None = None


class TtsStartPayload(BaseModel):
    """Server → client, on `tts.start`. §25.4: 'Tara's replies arrive as voice-note bubbles rendered from her TTS with transcript toggle'. Emitted after her `captions.final`, so the transcript the toggle shows is on screen before any audio plays — and is the same validated text the audio was rendered from, not a second generation.

`tts_audio_asset_id` became OPTIONAL in M9-P10b, and the null is load-bearing rather than lax. A voice NOTE is synthesised whole and stored, so it has an asset and a bubble that can replay it. A live CALL is streamed and its audio is never stored at all (§13, §33.1) — so there is no asset, and there is nothing to replay. Null is the type saying exactly that. Carrying an invented id would have promised a playback control over audio that does not exist anywhere.

`holding` marks §25.3's holding phrase — the line she speaks when §9 has out-run HOLDING_PHRASE_AFTER_MS. It is her voice but it is NOT her answer, and that difference is load-bearing on three separate paths (see the field)."""

    model_config = ConfigDict(frozen=True)

    client_message_id: str
    tts_audio_asset_id: str | None = None
    sample_rate_hz: int
    voice_id: str | None = None
    holding: bool = False


class TtsChunkMetaPayload(BaseModel):
    """Server → client, on `tts.chunk_meta`. §13 — shapes, never content. There is deliberately no text field: the words already crossed on `captions.final`, and a second copy travelling beside the audio is a second thing to keep in step with the validators."""

    model_config = ConfigDict(frozen=True)

    client_message_id: str
    seq: int
    byte_length: int


class TtsEndPayload(BaseModel):
    """Server → client, on `tts.end`. Total duration for the bubble's scrubber, and the signal that no further chunk meta is coming.

`holding` repeats `tts.start`'s flag so each event is self-describing. The client could infer it by remembering the start, but then the meaning of an `end` would depend on a `start` it might not have seen — and the branch it drives is whether the screen goes back to `thinking` or to `listening`, which is the difference between showing a mic-live indicator over a live turn and not."""

    model_config = ConfigDict(frozen=True)

    client_message_id: str
    duration_ms: int
    holding: bool = False


class BargeInPayload(BaseModel):
    """Server → client (§25.3, §7.3). Typed in M9-P10b because M9-P10b is the first milestone that emits it — the rule this package keeps, and the reason it stayed untyped through M9.

**It replaces `tts.end`, it does not precede it.** `tts.end` carries the total duration for the bubble's scrubber; an utterance that was cut has no total duration that was ever true, and sending one would put a scrubber on audio the user interrupted. So a synthesis stream ends in exactly one of two members and a client can rely on that.

`cancelled_after_chunk_seq` is the last `tts.chunk_meta.seq` the server sent before it stopped. The client needs it because it is buffering ahead of playback: without it, dropping 'the rest' is a guess about what the server had already put on the wire, and audio kept playing after the interruption is exactly the thing §25.3's barge-in exists to prevent."""

    model_config = ConfigDict(frozen=True)

    cancelled_client_message_id: str
    cancelled_after_chunk_seq: int | None = None
    reason: BargeInReason


class EntitlementWarningPayload(BaseModel):
    """Server → client (§7.3, §32.9). §32.9: warnings at 5 and 2 minutes, in-locale, in Tara's voice, ONCE EACH — the once-each is enforced by the session, not by the client ignoring repeats.

`minutes_left` is the threshold that fired, not a live countdown: a per-second remaining-minutes feed would be §29.2's countdown, which this product does not build. `minutes_quota` is null for the unlimited fair-use tiers, which is also what makes the §25.3 plan chip render '⏳ unlimited' rather than a number.

`message_key` and not a sentence: §2.4 puts every user-facing string in the catalogs, and a sentence on the wire is a sentence no §14 reviewer saw."""

    model_config = ConfigDict(frozen=True)

    minutes_left: int
    minutes_quota: int | None = None
    plan: str
    message_key: str


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
