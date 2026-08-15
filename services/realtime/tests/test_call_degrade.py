"""The §25.3 degrade ladder — written before the ladder was (M9-P10b).

**The invariant under test is one sentence: a dropped call must never lose what
was said.** Everything below is a different way of dropping it.

That sentence is harder here than anywhere else in the product, and the reason
is §33.1: call audio is NEVER stored. A voice note that fails to transcribe
still has its recording (§28.3 keeps it and offers "send as text?"). A typed
message that fails still sits in the composer. A spoken sentence in a call that
fails has neither — there is no audio to fall back on and no draft to resend
from. If the transcript is not already in the thread when the failure lands, the
words are gone, and no amount of retrying gets them back.

So each test here drives a real socket to a real failure and then asks the same
two questions: did the words survive, and did the user land somewhere designed?

Where the fakes are, and why they are there
--------------------------------------------

The socket the BROWSER speaks is real — `TestClient.websocket_connect` performs
a real upgrade and a real close, for the reason `apps/web/scripts/stub-realtime.mjs`
records at length: a suite that replaces the transport verifies frame handling
over a connection that was never opened.

What is faked is the media socket to `sitara-api`, at the client-object seam —
the same seam `test_chat_socket.py` fakes with `httpx.MockTransport`. The far
side of that seam is exercised for real in
`services/api/tests/calls/test_media_socket.py`, against the real FastAPI route.
Neither test fakes both ends of the same hop.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sitara_schemas import ControlEventType
from sitara_schemas.call_media import CallDownFrame, CallUpFrame

from call_harness import (
    AUDIO,
    REDEEM,
    SPOKEN,
    TURN,
    FakeMedia,
    _drain,
    _speak,
    _start,
    _types,
)
from sitara_realtime.main import app

# ---------------------------------------------------------------------------
# The chaos path: synthesis dies mid-utterance
# ---------------------------------------------------------------------------


def test_tts_dying_mid_call_lands_in_a_text_handoff_with_the_words_intact(
    media: FakeMedia,
) -> None:
    """§8's ladder, §25.3's degrade, and the sentence at the top of this file.

    The provider dies AFTER her reply has been validated and BEFORE the audio
    finishes. Three things must be true when the dust settles:

    1. Her words already crossed, on `captions.final`, before a single byte of
       audio — so the reply is on screen and the user has it.
    2. The audio stops deliberately, with a reason: `barge_in` carrying
       `provider_failed`, never a `tts.end` (which would put a scrubber on an
       utterance that never finished) and never silence.
    3. The call ends in `handoff.to_text` naming the conversation, because a
       call in which Tara cannot speak is not a call — it is a chat, and saying
       so is the honest state rather than a mute portrait.
    """
    with TestClient(app).websocket_connect("/call/session") as ws:
        _start(ws)
        assert _drain(ws, until="session.ready")

        _speak(media)
        media.push(CallDownFrame.TURN, client_message_id="u1", turn=TURN)
        media.push(CallDownFrame.TTS_START, client_message_id="u1", sample_rate_hz=16_000)
        media.push_audio(b"\x00\x01" * 160)
        media.push(
            CallDownFrame.TTS_CANCELLED,
            client_message_id="u1",
            after_chunk_seq=0,
            reason="provider_failed",
        )

        events = _drain(ws, until="handoff.to_text")

    kinds = _types(events)

    # (1) the user's words, then hers, then any audio. Ordering, not presence.
    user_final = next(
        i for i, e in enumerate(events)
        if e["type"] == "captions.final" and e["payload"].get("role") == "user"
    )
    tara_final = next(
        i for i, e in enumerate(events)
        if e["type"] == "captions.final" and e["payload"].get("role") == "tara"
    )
    assert user_final < tara_final < kinds.index("tts.start")
    assert events[user_final]["payload"]["text"] == SPOKEN
    assert events[tara_final]["payload"]["turn"]["text"] == TURN["text"]

    # (2) the cut is announced, with a true reason, and no tts.end pretends
    #     the utterance completed.
    assert "tts.end" not in kinds
    barge = events[kinds.index("barge_in")]
    assert barge["payload"]["reason"] == "provider_failed"
    assert barge["payload"]["cancelled_client_message_id"] == "u1"

    # (3) somewhere designed, naming the thread the words are in.
    handoff = events[-1]
    assert handoff["payload"]["conversation_id"] == REDEEM["conversation_id"]
    assert handoff["payload"]["reason"] == "tts_provider_failed"


def test_the_handoff_reports_itself_to_the_release_gate(media: FakeMedia) -> None:
    """§33.5's `network-recovery handoff success ≥98%`, measured (§43.5).

    A handoff that carried the conversation forward is a SUCCESS by §33.5's
    reading, and it has to be counted as one at the moment it happens — a
    number reconstructed later from logs is a number nobody trusts enough to
    launch on.
    """
    with TestClient(app).websocket_connect("/call/session") as ws:
        _start(ws)
        _drain(ws, until="session.ready")
        _speak(media)
        media.push(CallDownFrame.TURN, client_message_id="u1", turn=TURN)
        media.push(
            CallDownFrame.TTS_CANCELLED,
            client_message_id="u1",
            after_chunk_seq=None,
            reason="provider_failed",
        )
        _drain(ws, until="handoff.to_text")

    reported = {
        (f["observation"], f.get("value", 1.0)) for f in media.frames(CallUpFrame.METRIC)
    }
    assert ("recovery_attempt", 1.0) in reported
    assert ("recovery_succeeded", 1.0) in reported


# ---------------------------------------------------------------------------
# The other ways it breaks
# ---------------------------------------------------------------------------


def test_the_pipeline_dying_still_leaves_the_users_words_in_the_thread(
    media: FakeMedia,
) -> None:
    """The failure the whole `commit_utterance` ordering exists for.

    §9 dies between "she heard you" and "she answered". The user's own words
    must already have crossed as `captions.final` — which is what proves they
    were committed before the pipeline ran — and the call must degrade rather
    than sit there looking like it is still thinking.
    """
    with TestClient(app).websocket_connect("/call/session") as ws:
        _start(ws)
        _drain(ws, until="session.ready")
        _speak(media)
        media.push(
            CallDownFrame.ERROR,
            code="SYS_UNAVAILABLE",
            message_key="errors.sys.unavailable",
            client_message_id="u1",
        )
        events = _drain(ws, until="handoff.to_text")

    said = [
        e for e in events
        if e["type"] == "captions.final" and e["payload"].get("role") == "user"
    ]
    assert [e["payload"]["text"] for e in said] == [SPOKEN]
    assert events[-1]["payload"]["reason"] == "turn_failed"


def test_the_recogniser_dying_is_a_handoff_and_never_a_silent_call(
    media: FakeMedia,
) -> None:
    """STT dies before anything was said.

    Nothing is lost because nothing was said yet — but a call whose microphone
    has stopped reaching a recogniser must not keep drawing a listening
    indicator. §25.3's ladder has a designed state for this and silence is not
    it.
    """
    with TestClient(app).websocket_connect("/call/session") as ws:
        _start(ws)
        _drain(ws, until="session.ready")
        media.push(
            CallDownFrame.ERROR,
            code="VOICE_PROVIDER_UNAVAILABLE",
            message_key="errors.voice.provider_unavailable",
        )
        events = _drain(ws, until="handoff.to_text")

    assert events[-1]["payload"]["reason"] == "stt_provider_failed"
    assert "error" in _types(events), "the §34.4 envelope is forwarded, not swallowed"


def test_an_exhausted_minute_pool_hands_off_and_never_drops(media: FakeMedia) -> None:
    """§32.9: "at zero → auto text handoff with full context ... never a hard drop"."""
    with TestClient(app).websocket_connect("/call/session") as ws:
        _start(ws)
        _drain(ws, until="session.ready")
        _speak(media)
        media.push(CallDownFrame.TURN, client_message_id="u1", turn=TURN)
        media.push(CallDownFrame.EXHAUSTED, plan="monthly")
        events = _drain(ws, until="handoff.to_text")

    assert events[-1]["payload"]["reason"] == "entitlement_exhausted"
    said = [
        e for e in events
        if e["type"] == "captions.final" and e["payload"].get("role") == "tara"
    ]
    assert said, "her last answer is delivered before the pool cuts the call"


def test_a_dropped_socket_returns_the_answer_rather_than_the_question(
    media: FakeMedia,
) -> None:
    """§32.11, and the reason the resume buffer exists at all.

    The socket dies with a completed turn in hand. A reconnect inside five
    minutes must get the ANSWER back — never re-run the turn, which would
    charge the user twice for one question and could answer the same words
    differently the second time.
    """
    client = TestClient(app)
    with client.websocket_connect("/call/session") as ws:
        _start(ws)
        ready = _drain(ws, until="session.ready")[-1]
        token = ready["payload"]["resume_token"]
        _speak(media)
        media.push(CallDownFrame.TURN, client_message_id="u1", turn=TURN)
        _drain(ws, until="captions.final")
        _drain(ws, until="captions.final")

    with client.websocket_connect("/call/session") as ws:
        _start(ws, resume_token=token)
        events = _drain(ws, until="session.ready")

    offer = next(e for e in events if e["type"] == "resume.offer")
    assert offer["payload"]["pending_turn"]["text"] == TURN["text"]
    assert offer["payload"]["conversation_id"] == REDEEM["conversation_id"]


# ---------------------------------------------------------------------------
# The protocol itself
# ---------------------------------------------------------------------------


def test_a_call_invents_no_control_event(media: FakeMedia) -> None:
    """§34.6's set is closed at fifteen and M9-P10b added none of it.

    The milestone that would most plausibly have needed a sixteenth member is
    this one — it is the first to stream audio, meter minutes and duck a
    speaker. It says all three in members that already existed, which is what
    §34.6 claimed and what this asserts rather than assumes.
    """
    with TestClient(app).websocket_connect("/call/session") as ws:
        _start(ws)
        _drain(ws, until="session.ready")
        _speak(media)
        media.push(CallDownFrame.TURN, client_message_id="u1", turn=TURN)
        media.push(CallDownFrame.TTS_START, client_message_id="u1", sample_rate_hz=16_000)
        media.push_audio(b"\x00\x01" * 320)
        media.push(CallDownFrame.TTS_END, client_message_id="u1", chunks=1)
        events = _drain(ws, until="tts.end")

    closed = {t.value for t in ControlEventType}
    assert set(_types(events)) - {AUDIO} <= closed
    assert AUDIO in _types(events), "her audio really did stream over the socket"
    assert "tts.chunk_meta" in _types(events), (
        "a call really does stream, so the member a NOTE could not honestly "
        "emit is finally emitted here"
    )
