"""GENERATED FILE — do not edit. Source: packages/schemas/src/*.json (run scripts/generate.py).

SPEC §33.1 / §6.4 / §25.4 — the vocabulary of a voice note.

`sitara_api.chat_orchestration.store` writes `transcript_status` and
`playback_policy` onto every message row; `apps/web`'s VoiceNoteBubble
renders them. They held different sets until M9 — see the source JSON.
"""

from enum import StrEnum

__all__ = [
    "MAX_NOTE_DURATION_MS",
    "PLAYBACK_POLICIES",
    "PlaybackPolicy",
    "SOURCE_AUDIO_RETENTION_DAYS",
    "TRANSCRIPT_STATUSES",
    "TranscriptStatus",
    "VAD_STATES",
    "VadState",
]


class TranscriptStatus(StrEnum):
    """§6.4's `messages.transcript_status`, one of §33.1's six explicit fields. `not_applicable` is a TYPED message — the field is required on every message row, so text needs a member that says 'this was never spoken' rather than a null that reads as 'transcription is still coming'. §28.3's failure row is `failed`: 'transcribe-fail → send as text? original audio preserved' — the audio survives a failed transcript, which is why this is a status and not a delete trigger."""

    NOT_APPLICABLE = "not_applicable"
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


TRANSCRIPT_STATUSES: tuple[TranscriptStatus, ...] = (
    TranscriptStatus.NOT_APPLICABLE,
    TranscriptStatus.PENDING,
    TranscriptStatus.READY,
    TranscriptStatus.FAILED,
)


class PlaybackPolicy(StrEnum):
    """§6.4's `messages.playback_policy`, and the field §25.4's central promise rests on: 'replay plays the user's ORIGINAL recording per the §33.1 storage policy, never a TTS reconstruction'. That sentence is only enforceable if a bubble can tell the three cases apart, which is what this enum is for. `synthesised` is the ONLY member under which audio is a reconstruction, and §25.4 makes it illegal on a user message — a rule the store enforces structurally rather than by review."""

    TEXT_ONLY = "text_only"
    ORIGINAL_AUDIO = "original_audio"
    TRANSCRIPT_ONLY = "transcript_only"
    SYNTHESISED = "synthesised"


PLAYBACK_POLICIES: tuple[PlaybackPolicy, ...] = (
    PlaybackPolicy.TEXT_ONLY,
    PlaybackPolicy.ORIGINAL_AUDIO,
    PlaybackPolicy.TRANSCRIPT_ONLY,
    PlaybackPolicy.SYNTHESISED,
)


class VadState(StrEnum):
    """§34.6's `vad.state` payload. In M9 this brackets a HELD recording rather than reporting server-side voice activity detection — §25.4's grammar is hold-to-record or tap-lock, so the client knows when speech starts and stops because the user's finger says so. M10's live calls add the server-VAD sense of the same member (§25.3's barge-in ducking); the members below are chosen so that addition is a widening, not a rename."""

    SPEECH_START = "speech_start"
    SPEECH_END = "speech_end"
    CANCELLED = "cancelled"


VAD_STATES: tuple[VadState, ...] = (
    VadState.SPEECH_START,
    VadState.SPEECH_END,
    VadState.CANCELLED,
)


#: §33.1 — 'the original recording is stored encrypted for 30 days BY DEFAULT'. Default, so a user setting may shorten it; the expiry job reads the per-note `source_audio_expires_at` rather than this constant, which exists so both sides can render the same promise in the same words.
SOURCE_AUDIO_RETENTION_DAYS = 30

#: A cap, not a spec value. §34.6's frame is 16kHz mono s16le = 32 kB/s, so two minutes is ~3.8 MB — comfortably inside MongoDB's 16 MB document limit, which is where §33.1's CSFLE key class puts the bytes. The client stops recording here rather than letting a pocket-dial write a document that cannot be stored.
MAX_NOTE_DURATION_MS = 120000
