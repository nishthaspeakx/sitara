"""Binary frames on the chat socket (M9, §34.6/§33.1/§28.3).

Through M8 the rule was "binary is refused until M9, because a socket that
quietly accepts PCM has opened a §33.1 storage question nobody asked". M9
answered the question, and the replacement rule is deliberately NARROWER than
"accepted": PCM is admissible only inside a `vad.state` bracket. The bracket is
what binds a run of bytes to a client_message_id, a locale and a consent
posture — audio arriving with none of those attached is audio nobody can
account for, and §33.1 is a section about being able to account for audio.

As with the text socket, the API is stubbed at its HTTP boundary. This service's
job is the PROTOCOL: it holds no STT, no pipeline and no database.
"""

from __future__ import annotations

import json
import struct
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sitara_schemas import BINARY_HEADER_BYTES, ControlEventType

from sitara_realtime import chat as chat_mod
from sitara_realtime.chat import ResumeBuffer
from sitara_realtime.config import Settings
from sitara_realtime.main import app

# `tests/` has no `__init__.py` here, so pytest puts the directory on the path
# and modules import by bare name — `tests.test_chat_socket` does not resolve.
from test_chat_socket import REDEEM, TURN, _events, _start

PCM = b"\x00\x01" * 800


def frame(seq: int, pcm: bytes = PCM, flags: int = 0) -> bytes:
    return struct.pack(">II", seq, flags) + pcm


TRANSCRIPT = {
    "client_message_id": "m1",
    "text": "Mera rahu kaal kab hai aaj?",
    "transcript_status": "ready",
    "playback_policy": "original_audio",
    "source_audio_asset_id": "6a70000000000000000000e1",
    "duration_ms": 1200,
    "source_audio_expires_at": "2026-09-12T09:30:00+00:00",
    "quoted_message_id": None,
}

TTS = {
    "start": {
        "client_message_id": "m1",
        "tts_audio_asset_id": "6a70000000000000000000e2",
        "sample_rate_hz": 16000,
        "voice_id": None,
    },
    "end": {"client_message_id": "m1", "duration_ms": 3400},
}


class StubVoiceApi:
    """`POST /v1/chat/ws/voice-note` as the wire really serves it."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.stages = ["transcription", "safety_pre", "generation"]
        self.transcript: dict | None = dict(TRANSCRIPT)
        self.turn: dict | None = dict(TURN)
        self.tts: dict | None = dict(TTS)
        self.fail: dict | None = None

    async def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/chat/ws/redeem":
            return httpx.Response(200, json=REDEEM)
        if request.url.path == "/v1/chat/ws/voice-note":
            self.calls.append(json.loads(request.content))
            lines = [json.dumps({"stage": s}) for s in self.stages]
            if self.fail is not None:
                lines.append(json.dumps({"error": self.fail}))
            else:
                if self.transcript is not None:
                    lines.append(json.dumps({"transcript": self.transcript}))
                if self.turn is not None:
                    lines.append(json.dumps({"turn": self.turn}))
                if self.tts is not None:
                    lines.append(json.dumps({"tts": self.tts}))
            return httpx.Response(200, text="\n".join(lines) + "\n")
        raise AssertionError(f"unexpected call: {request.url.path}")


@pytest.fixture()
def voice_api(monkeypatch: pytest.MonkeyPatch) -> StubVoiceApi:
    stub = StubVoiceApi()
    real_client = httpx.AsyncClient

    def build(*args: object, **kwargs: object) -> httpx.AsyncClient:
        return real_client(
            transport=httpx.MockTransport(stub.handler),
            base_url=str(kwargs.get("base_url", "http://api")),
        )

    monkeypatch.setattr(chat_mod.httpx, "AsyncClient", build)
    app.state.settings = Settings(service_key="k", api_base_url="http://api")
    app.state.resume_buffer = ResumeBuffer()
    return stub


def _vad(ws: Any, state: str, seq: int, cid: str = "m1", **extra: Any) -> None:
    ws.send_text(
        json.dumps(
            {
                "type": "vad.state",
                "seq": seq,
                "ts": 0,
                "payload": {"state": state, "client_message_id": cid, **extra},
            }
        )
    )


# ---------------------------------------------------------------------------
# The bracket


def test_binary_outside_a_bracket_is_still_refused(voice_api: StubVoiceApi) -> None:
    """The M8 rule survives where it still applies. PCM with no `vad.state`
    before it belongs to no message and carries no consent posture."""
    with TestClient(app).websocket_connect("/chat/session") as ws:
        _start(ws)
        _events(ws, 1)  # session.ready

        ws.send_bytes(frame(0))

        (event,) = _events(ws, 1)
        assert event["type"] == ControlEventType.ERROR
        assert event["payload"]["code"] == "SYS_VALIDATION"
        assert not voice_api.calls


def test_a_bracketed_note_reaches_the_api_as_the_bytes_that_were_sent(
    voice_api: StubVoiceApi,
) -> None:
    """The whole path, and the assertion §25.4 rests on at this layer: the
    frames reassemble to exactly what the client sent, in order."""
    import base64

    with TestClient(app).websocket_connect("/chat/session") as ws:
        _start(ws)
        _events(ws, 1)

        _vad(ws, "speech_start", seq=1)
        chunks = [bytes([i, i]) * 100 for i in range(4)]
        for seq, chunk in enumerate(chunks):
            ws.send_bytes(frame(seq, chunk))
        _vad(ws, "speech_end", seq=2)

        events = _events(ws, 6)  # 3 presence + user caption + tara caption + tts.start
        # `tts.end` follows; drain it so the socket closes cleanly.
        events += _events(ws, 1)

    assert len(voice_api.calls) == 1
    sent = base64.b64decode(voice_api.calls[0]["audio_b64"])
    assert sent == b"".join(chunks)
    assert voice_api.calls[0]["sample_rate_hz"] == 16000
    assert voice_api.calls[0]["client_message_id"] == "m1"


def test_the_users_own_bubble_arrives_before_hers(voice_api: StubVoiceApi) -> None:
    """§25.4's thread order. The transcript belongs to a bubble the user can
    already see; her reply answers it. Reversed, the thread would show an
    answer to a question that had not appeared yet."""
    with TestClient(app).websocket_connect("/chat/session") as ws:
        _start(ws)
        _events(ws, 1)
        _vad(ws, "speech_start", seq=1)
        ws.send_bytes(frame(0))
        _vad(ws, "speech_end", seq=2)
        events = _events(ws, 7)

    captions = [e for e in events if e["type"] == ControlEventType.CAPTIONS_FINAL]
    assert [c["payload"]["role"] for c in captions] == ["user", "tara"]
    assert captions[0]["payload"]["text"] == TRANSCRIPT["text"]
    assert captions[0]["payload"]["source_audio_asset_id"] == TRANSCRIPT["source_audio_asset_id"]
    assert captions[0]["payload"]["playback_policy"] == "original_audio"


def test_tts_events_follow_her_words_never_precede_them(voice_api: StubVoiceApi) -> None:
    """§25.4's transcript toggle must have something to show before audio
    plays — and it must be the same validated text the audio was rendered
    from. Emitting `tts.start` first would give the bubble a play control over
    words that had not arrived."""
    with TestClient(app).websocket_connect("/chat/session") as ws:
        _start(ws)
        _events(ws, 1)
        _vad(ws, "speech_start", seq=1)
        ws.send_bytes(frame(0))
        _vad(ws, "speech_end", seq=2)
        events = _events(ws, 7)

    types = [e["type"] for e in events]
    tara_caption = max(
        i for i, e in enumerate(events)
        if e["type"] == ControlEventType.CAPTIONS_FINAL and e["payload"]["role"] == "tara"
    )
    assert types.index(ControlEventType.TTS_START) > tara_caption
    assert types.index(ControlEventType.TTS_END) > types.index(ControlEventType.TTS_START)
    # No fabricated chunk metering: a note is synthesised whole, so there are
    # no chunks. M10's streamed call audio is what that member is for.
    assert ControlEventType.TTS_CHUNK_META not in types


# ---------------------------------------------------------------------------
# The failures that matter


def test_a_sequence_gap_fails_the_note_rather_than_splicing_it(
    voice_api: StubVoiceApi,
) -> None:
    """The defect no downstream validator could catch.

    A note missing its middle still transcribes — into a fluent sentence the
    user never said, which then goes to §9 as their question and gets answered.
    §9 gates what TARA says; this fabrication is on the user's side of the turn.
    """
    with TestClient(app).websocket_connect("/chat/session") as ws:
        _start(ws)
        _events(ws, 1)
        _vad(ws, "speech_start", seq=1)
        ws.send_bytes(frame(0))
        ws.send_bytes(frame(2))  # 1 never arrived

        (event,) = _events(ws, 1)
        assert event["payload"]["code"] == "SYS_VALIDATION"

        # And the bracket is gone, so the client cannot "continue" into a note
        # that already lost its middle.
        ws.send_bytes(frame(3))
        (second,) = _events(ws, 1)
        assert second["payload"]["code"] == "SYS_VALIDATION"

    assert not voice_api.calls


def test_a_truncated_frame_is_refused(voice_api: StubVoiceApi) -> None:
    """A half sample shifts every later sample by a byte and turns the rest of
    the note into noise — which STT transcribes as *something*."""
    with TestClient(app).websocket_connect("/chat/session") as ws:
        _start(ws)
        _events(ws, 1)
        _vad(ws, "speech_start", seq=1)
        ws.send_bytes(struct.pack(">II", 0, 0) + b"\x01\x02\x03")

        (event,) = _events(ws, 1)
        assert event["payload"]["code"] == "SYS_VALIDATION"
    assert not voice_api.calls


def test_the_cancel_slide_sends_nothing_anywhere(voice_api: StubVoiceApi) -> None:
    """§28.3's cancel-slide. Not transcribed, not stored, not uploaded — the
    bytes simply stop existing, which is the only reading of "cancel" a user
    would accept for something they said out loud."""
    with TestClient(app).websocket_connect("/chat/session") as ws:
        _start(ws)
        _events(ws, 1)
        _vad(ws, "speech_start", seq=1)
        ws.send_bytes(frame(0))
        ws.send_bytes(frame(1))
        _vad(ws, "cancelled", seq=2)

        # Nothing is emitted and nothing is uploaded; the socket stays live.
        _vad(ws, "speech_start", seq=3, cid="m2")
        ws.send_bytes(frame(0))
        _vad(ws, "speech_end", seq=4, cid="m2")
        _events(ws, 7)

    assert len(voice_api.calls) == 1
    assert voice_api.calls[0]["client_message_id"] == "m2"


def test_an_empty_bracket_is_refused(voice_api: StubVoiceApi) -> None:
    """A `speech_end` with no audio would upload an empty note, which STT
    would answer with silence and §9 would run on an empty string."""
    with TestClient(app).websocket_connect("/chat/session") as ws:
        _start(ws)
        _events(ws, 1)
        _vad(ws, "speech_start", seq=1)
        _vad(ws, "speech_end", seq=2)

        (event,) = _events(ws, 1)
        assert event["payload"]["code"] == "SYS_VALIDATION"
    assert not voice_api.calls


def test_a_bracket_without_a_message_id_is_refused(voice_api: StubVoiceApi) -> None:
    """Without it the PCM about to arrive belongs to no bubble, and the
    transcript would appear in the thread from nowhere."""
    with TestClient(app).websocket_connect("/chat/session") as ws:
        _start(ws)
        _events(ws, 1)
        _vad(ws, "speech_start", seq=1, cid="")

        (event,) = _events(ws, 1)
        assert event["payload"]["code"] == "SYS_VALIDATION"
        # ...and no bracket was opened, so PCM is still refused.
        ws.send_bytes(frame(0))
        (second,) = _events(ws, 1)
        assert second["payload"]["code"] == "SYS_VALIDATION"


def test_a_failed_transcription_keeps_the_bubble_and_raises_no_error(
    voice_api: StubVoiceApi,
) -> None:
    """§28.3: "transcribe-fail → 'send as text?' original audio preserved".

    That is a designed state carried on the user's own bubble — not an error
    envelope, which would render §34.4's retry affordance over a note that was
    successfully recorded and successfully stored.
    """
    voice_api.transcript = dict(
        TRANSCRIPT, text="", transcript_status="failed", playback_policy="original_audio"
    )
    voice_api.turn = None
    voice_api.tts = None

    with TestClient(app).websocket_connect("/chat/session") as ws:
        _start(ws)
        _events(ws, 1)
        _vad(ws, "speech_start", seq=1)
        ws.send_bytes(frame(0))
        _vad(ws, "speech_end", seq=2)
        events = _events(ws, 4)  # 3 presence + the user's caption

    assert not [e for e in events if e["type"] == ControlEventType.ERROR]
    caption = events[-1]
    assert caption["payload"]["transcript_status"] == "failed"
    # The recording survived, which is the half of §28.3 that matters.
    assert caption["payload"]["source_audio_asset_id"]


def test_one_note_at_a_time(voice_api: StubVoiceApi) -> None:
    """Same rule the text socket has: a second note mid-flight is refused
    rather than interleaved into one thread."""
    import asyncio

    with TestClient(app).websocket_connect("/chat/session") as ws:
        _start(ws)
        _events(ws, 1)
        _vad(ws, "speech_start", seq=1)
        ws.send_bytes(frame(0))
        _vad(ws, "speech_end", seq=2)
        _events(ws, 7)  # drain the first, completed note

        # A note that arrives while the first is still uploading would need the
        # stub held open; the guard is the same `turn_task` the text path uses
        # and `test_chat_socket.py` already holds a turn open to prove it. Here
        # the honest assertion is that a completed note frees the slot.
        _vad(ws, "speech_start", seq=3, cid="m2")
        ws.send_bytes(frame(0))
        _vad(ws, "speech_end", seq=4, cid="m2")
        _events(ws, 7)

    assert len(voice_api.calls) == 2


def test_the_header_size_comes_from_the_schema_not_a_literal() -> None:
    """§34.6's 8-byte header is declared once, in packages/schemas. A literal
    here would be a second declaration, and the two would drift the way every
    other closed set in that package drifted before it moved there."""
    assert BINARY_HEADER_BYTES == 8
    assert len(frame(0, b"")) == BINARY_HEADER_BYTES
