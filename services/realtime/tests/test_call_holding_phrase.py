"""§25.3's holding phrase, across the hop that carries it.

"thinking (brief shimmer on the waveform — max 1.8s before she speaks a holding
phrase)". §9 runs three model round-trips in series, so a real reply is often
~5.8 seconds; the phrase is what turns four seconds of nothing into a pause
somebody designed.

`sitara-api` decides to speak it and this service forwards it. What this file
protects is the ONE thing that goes silently wrong when it does: the phrase is
audio, and §33.5's `first_audio_seconds` measures audio.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sitara_schemas.call_media import CallDownFrame, CallUpFrame

from call_harness import TURN, FakeMedia, _drain, _speak, _start
from sitara_realtime.main import app


@pytest.fixture()
def media(monkeypatch: pytest.MonkeyPatch) -> FakeMedia:
    from call_harness import make_media_fixture

    return make_media_fixture(monkeypatch)


def _observations(media: FakeMedia) -> set[str]:
    return {f["observation"] for f in media.frames(CallUpFrame.METRIC)}


def test_the_phrase_does_not_become_the_latency_the_gate_reads(media: FakeMedia) -> None:
    """The reason the flag exists at all.

    §33.5's `first_audio_seconds` measures the moment a user's utterance was
    finalised to the moment HER ANSWER begins. A holding phrase arriving at 1.8
    seconds would report 1.8 for a reply that took 5.8 — turning the cheapest
    sound in the system to produce into the number a release gate reads, and
    making the measure impossible to fail.

    `call_metrics` and `call_gate` are separate files precisely so a gate cannot
    be made to pass by changing how the evidence is counted. This is that rule
    one layer down.
    """
    with TestClient(app).websocket_connect("/call/session") as ws:
        _start(ws)
        _speak(media)

        media.push(CallDownFrame.TTS_START, client_message_id="u1", holding=True)
        media.push_audio(b"\x00\x01" * 64)
        media.push(CallDownFrame.TTS_END, client_message_id="u1", chunks=1, holding=True)
        _drain(ws, until="tts.end")

        assert "first_audio_seconds" not in _observations(media), (
            "the holding phrase was timed as her answer"
        )

        # …and her real answer, when it arrives, IS timed.
        media.push(CallDownFrame.TURN, client_message_id="u1", turn=TURN)
        media.push(CallDownFrame.TTS_START, client_message_id="u1")
        media.push_audio(b"\x00\x01" * 64)
        _drain(ws, until="tts.chunk_meta")

        assert "first_audio_seconds" in _observations(media), (
            "her answer was not timed because the phrase had consumed the flag"
        )


def test_the_flag_reaches_the_browser(media: FakeMedia) -> None:
    """The client branches on it: a phrase ends back in `thinking`, her answer
    ends in `listening`. Dropping the flag here would put a mic-live indicator
    over a turn §9 is still working on — and §7.3 would then refuse whatever
    the user said into it."""
    with TestClient(app).websocket_connect("/call/session") as ws:
        _start(ws)
        _speak(media)
        media.push(CallDownFrame.TTS_START, client_message_id="u1", holding=True)
        media.push(CallDownFrame.TTS_END, client_message_id="u1", chunks=0, holding=True)
        events = _drain(ws, until="tts.end")

    start = next(e for e in events if e["type"] == "tts.start")
    end = next(e for e in events if e["type"] == "tts.end")
    assert start["payload"]["holding"] is True
    assert end["payload"]["holding"] is True


def test_an_ordinary_reply_still_says_nothing_about_holding(media: FakeMedia) -> None:
    """`holding` defaults to false, so every producer that predates it — and the
    whole voice-note path, which has no such thing — is unchanged."""
    with TestClient(app).websocket_connect("/call/session") as ws:
        _start(ws)
        _speak(media)
        media.push(CallDownFrame.TURN, client_message_id="u1", turn=TURN)
        media.push(CallDownFrame.TTS_START, client_message_id="u1")
        media.push(CallDownFrame.TTS_END, client_message_id="u1", chunks=1)
        events = _drain(ws, until="tts.end")

    start = next(e for e in events if e["type"] == "tts.start")
    assert start["payload"]["holding"] is False


def test_the_utterance_survives_the_phrase(media: FakeMedia) -> None:
    """A holding phrase's `tts.end` must not close the utterance — §9 is still
    working on the answer that same utterance asked for.

    Clearing it would orphan the answer's chunk metadata and throw away the
    start time `first_audio_seconds` measures from, so the answer would arrive
    untimed and unattributed.
    """
    with TestClient(app).websocket_connect("/call/session") as ws:
        _start(ws)
        _speak(media)
        media.push(CallDownFrame.TTS_START, client_message_id="u1", holding=True)
        media.push(CallDownFrame.TTS_END, client_message_id="u1", chunks=0, holding=True)
        _drain(ws, until="tts.end")

        media.push(CallDownFrame.TURN, client_message_id="u1", turn=TURN)
        media.push(CallDownFrame.TTS_START, client_message_id="u1")
        media.push_audio(b"\x00\x01" * 32)
        events = _drain(ws, until="tts.chunk_meta")

    meta = next(e for e in events if e["type"] == "tts.chunk_meta")
    assert meta["payload"]["client_message_id"], "the answer's audio lost its utterance"
