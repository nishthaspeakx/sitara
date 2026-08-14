"""§25.3's barge-in, its VAD, and §32.9's metering.

"Barge-in = just speak (server-side VAD ducking)" is one sentence of §25.3 and
three separable claims, and they are tested separately here because they fail
separately:

- the DETECTOR has to tell a person from a room (`test_vad_*`);
- the SOCKET has to duck her audio when the detector fires, and only then
  (`test_barge_in_*`);
- and §33.5 has to end up with a number for how often that worked, because
  "barge-in success ≥95%" is one of the six measures that decide whether calls
  ship at all.

The third is the one that would quietly go missing. A barge-in that works is
invisible; a barge-in that is never counted is also invisible, and the two look
identical right up to the launch meeting.
"""

from __future__ import annotations

import math
import struct
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sitara_schemas.call_media import CallDownFrame, CallUpFrame

from call_harness import TURN, FakeMedia, _drain, _start, _types
from sitara_realtime.main import app
from sitara_realtime.vad import DEFAULT_SPEECH_RMS, FRAME_SAMPLES, SpeechDetector, rms


def pcm(amplitude: int, *, frames: int = 10) -> bytes:
    """A tone at a known amplitude — the only thing the detector reads."""
    samples = []
    for i in range(FRAME_SAMPLES * frames):
        samples.append(int(amplitude * math.sin(i * 0.1)))
    return struct.pack(f"<{len(samples)}h", *samples)


def wire(seq: int, payload: bytes) -> bytes:
    """§34.6's binary frame: 8-byte header (4B seq + 4B flags) then PCM."""
    return struct.pack(">II", seq, 0) + payload


# ---------------------------------------------------------------------------
# the detector
# ---------------------------------------------------------------------------


def test_vad_hears_a_person_and_not_a_quiet_room() -> None:
    detector = SpeechDetector()
    assert not detector.feed(pcm(60)), "room tone is not speech"
    assert detector.feed(pcm(6000)), "a person at arm's length is"


def test_vad_needs_more_than_one_loud_frame() -> None:
    """The whole defence against a cough, a door, a chair — and against her own
    voice leaking out of a phone speaker back into its microphone, which is the
    failure that makes a call unusable rather than merely annoying."""
    detector = SpeechDetector()
    assert not detector.feed(pcm(9000, frames=1)), "one 20ms burst is a noise"
    assert detector.feed(pcm(9000, frames=3)), "60ms of it is a voice"


def test_vad_holds_on_through_a_pause_inside_a_sentence() -> None:
    """Hangover is longer than onset on purpose: ending a speech window early
    clips someone mid-sentence, and ending it late costs nothing."""
    detector = SpeechDetector()
    detector.feed(pcm(9000, frames=5))
    assert detector.feed(pcm(0, frames=10)), "200ms of silence is a breath"
    assert not detector.feed(pcm(0, frames=30)), "600ms of it is the end"


def test_rms_survives_a_truncated_sample() -> None:
    """An odd trailing byte is half a sample, not a quiet one. `array.frombytes`
    would raise on it, and a raise here would take a call down over one byte."""
    assert rms(b"\x00") == 0.0
    assert rms(pcm(8000) + b"\x7f") >= DEFAULT_SPEECH_RMS


# ---------------------------------------------------------------------------
# the socket
# ---------------------------------------------------------------------------


def _live_call(ws: Any, media: FakeMedia) -> None:
    """Get to the state that matters: she is mid-sentence, audio flowing."""
    _start(ws)
    _drain(ws, until="session.ready")
    media.push(CallDownFrame.CAPTION, text="what is Saturn doing?", is_final=True)
    media.push(CallDownFrame.TURN, client_message_id="u1", turn=TURN)
    media.push(CallDownFrame.TTS_START, client_message_id="u1", sample_rate_hz=16_000)
    media.push_audio(b"\x00\x01" * 160)
    _drain(ws, until="tts.chunk_meta")


def test_speaking_over_her_cancels_the_synthesis(media: FakeMedia) -> None:
    """§7.3: "user speech cancels TTS stream, one in-flight utterance max".

    The cancel goes UP to `sitara-api`, because that is where the vendor socket
    is and stopping the stream means stopping the vendor — a client that merely
    muted its own speaker would keep paying for audio nobody hears and would
    leave her talking into the next question.
    """
    with TestClient(app).websocket_connect("/call/session") as ws:
        _live_call(ws, media)
        for seq in range(4):
            ws.send_bytes(wire(seq, pcm(9000, frames=3)))
        media.push(
            CallDownFrame.TTS_CANCELLED,
            client_message_id="u1",
            after_chunk_seq=0,
            reason="user_speech",
        )
        events = _drain(ws, until="barge_in")

    assert media.frames(CallUpFrame.CANCEL_SPEECH), "the vendor was never told to stop"
    barge = events[-1]
    assert barge["payload"]["reason"] == "user_speech"
    # The client is buffering ahead of playback, so "drop the rest" is only
    # actionable if it knows what the rest WAS.
    assert barge["payload"]["cancelled_after_chunk_seq"] == 0
    assert "tts.end" not in _types(events), (
        "a cut utterance has no total duration that was ever true"
    )


def test_silence_never_barges_in(media: FakeMedia) -> None:
    """The inverse, and the one that would ship broken.

    A detector that fired on room tone would cut Tara off every time the user
    breathed — and every test that only checks "barge-in works" passes with it.
    """
    with TestClient(app).websocket_connect("/call/session") as ws:
        _live_call(ws, media)
        for seq in range(6):
            ws.send_bytes(wire(seq, pcm(40, frames=5)))
        media.push(CallDownFrame.TTS_END, client_message_id="u1", chunks=1)
        _drain(ws, until="tts.end")

    assert not media.frames(CallUpFrame.CANCEL_SPEECH)


def test_a_barge_in_is_counted_for_the_release_gate(media: FakeMedia) -> None:
    """§33.5's `barge_in_success ≥95%` needs a numerator and a denominator.

    The ATTEMPT is reported when we ask the vendor to stop and the SUCCESS only
    when it confirms it did. Reporting both at the same moment would make the
    ratio 100% by construction — a measure that cannot fail, which is worse
    than no measure because it reads as evidence.
    """
    with TestClient(app).websocket_connect("/call/session") as ws:
        _live_call(ws, media)
        for seq in range(4):
            ws.send_bytes(wire(seq, pcm(9000, frames=3)))
        _drain(ws, until="vad.state")
        attempted = {f["observation"] for f in media.frames(CallUpFrame.METRIC)}
        assert "barge_in_attempt" in attempted
        assert "barge_in_stopped" not in attempted, (
            "success is claimed before the stream confirmed it stopped"
        )

        media.push(
            CallDownFrame.TTS_CANCELLED,
            client_message_id="u1",
            after_chunk_seq=0,
            reason="user_speech",
        )
        _drain(ws, until="barge_in")

    confirmed = {f["observation"] for f in media.frames(CallUpFrame.METRIC)}
    assert {"barge_in_attempt", "barge_in_stopped"} <= confirmed


def test_the_mic_going_live_is_announced_to_the_screen(media: FakeMedia) -> None:
    """§25.3's listening state: "listening loop + mic-live indicator".

    The bracket is opened by the SERVER here, not by a finger — that is the
    M10 sense `vad.state` was widened for, and the id it carries is minted here
    because server-side VAD is what noticed.
    """
    with TestClient(app).websocket_connect("/call/session") as ws:
        _start(ws)
        _drain(ws, until="session.ready")
        for seq in range(4):
            ws.send_bytes(wire(seq, pcm(9000, frames=3)))
        events = _drain(ws, until="vad.state")

    opened = events[-1]["payload"]
    assert opened["state"] == "speech_start"
    assert opened["client_message_id"], "the utterance has an id before it has words"


# ---------------------------------------------------------------------------
# §32.9's warnings
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("minutes", [5, 2])
def test_a_minute_warning_reaches_the_screen_in_a_key(
    media: FakeMedia, minutes: int
) -> None:
    """§32.9's two notices. The socket FORWARDS them and does not re-derive them.

    The quota lives in `sitara-api` and so does the arithmetic, including the
    once-each rule. A second implementation here would be a second opinion about
    when someone is nearly out of minutes, and the two would disagree on exactly
    the call where it matters.

    `message_key`, never a sentence: §2.4 puts every user-facing string in the
    catalogs, and a sentence on the wire is one no §14 reviewer saw.
    """
    with TestClient(app).websocket_connect("/call/session") as ws:
        _start(ws)
        _drain(ws, until="session.ready")
        media.push(
            CallDownFrame.ENTITLEMENT_WARNING,
            minutes_left=minutes,
            minutes_quota=300,
            plan="monthly",
            message_key="ui.call.warning_minutes",
        )
        events = _drain(ws, until="entitlement.warning")

    payload = events[-1]["payload"]
    assert payload["minutes_left"] == minutes
    assert payload["message_key"].startswith("ui.")
    # No value on this frame is a rendered sentence. A key has no spaces in it
    # and a sentence does — a crude test, and the exact crudeness wanted: it
    # catches the one regression that matters (somebody adding a `text` field
    # "so the client does not have to look it up") without pretending to know
    # what any particular catalog string will say.
    for field, value in payload.items():
        if isinstance(value, str):
            assert " " not in value, f"{field} carries prose, not a key: {value!r}"
