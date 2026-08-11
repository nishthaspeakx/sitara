"""`WS /chat/session` — the §34.6 protocol, and what happens when it breaks.

The API is stubbed here at the HTTP boundary, not the pipeline: this service's
job is the PROTOCOL, and what it must never do is invent a control-event type,
forward text that has not been validated, or answer a question twice because a
socket blinked. Those are all observable from outside.

The pipeline-side half of "a fabricated claim never reaches the bubble" lives
in `services/api/tests/chat/test_presenter.py`, over the real §9 pipeline.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sitara_schemas import ControlEventType, PresenceState

from sitara_realtime import chat as chat_mod
from sitara_realtime.chat import ResumeBuffer
from sitara_realtime.config import Settings
from sitara_realtime.main import app

TURN: dict[str, Any] = {
    "message_id": "6a70000000000000000000d1",
    "text": "Saturn is moving through your 10th house today. Go slowly.",
    "locale": "en",
    "confidence": "verified",
    "safety_level": "l1_clear",
    "presence_state": "calm_guidance",
    "intent": "natal_chart_question",
    "trace_id": "t1",
    "citations": [],
    "memory_chips": [],
    "review_queued": False,
    "message_key": None,
    "budget_notice_key": None,
}

REDEEM = {
    "ws_session": "ws-session-token",
    "user_id": "6a70000000000000000000a1",
    "conversation_id": "6a70000000000000000000c1",
    "locale": "en",
    "expires_in_s": 1800,
}


class StubApi:
    """`sitara-api` at its HTTP edge, with the NDJSON turn stream it really
    serves. Not a `page.route`-style intercept in spirit: the socket makes a
    real client call and this answers it as the wire does."""

    def __init__(self, *, stages: list[str] | None = None, fail: dict | None = None) -> None:
        self.stages = stages if stages is not None else ["safety_pre", "intent", "generation"]
        self.fail = fail
        self.turn_calls = 0
        self.redeem_status = 200
        #: Set to hold a turn open, so a second question genuinely arrives
        #: mid-flight rather than after the first has quietly finished.
        self.hold: asyncio.Event | None = None

    async def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/chat/ws/redeem":
            if self.redeem_status != 200:
                return httpx.Response(
                    self.redeem_status,
                    json={"code": "AUTH_INVALID_TOKEN", "message_key": "errors.auth.invalid_token"},
                )
            return httpx.Response(200, json=REDEEM)
        if request.url.path == "/v1/chat/ws/turn":
            self.turn_calls += 1
            if self.hold is not None:
                await self.hold.wait()
            lines = [json.dumps({"stage": s}) for s in self.stages]
            lines.append(json.dumps(self.fail if self.fail else {"turn": TURN}))
            return httpx.Response(200, text="\n".join(lines) + "\n")
        raise AssertionError(f"unexpected call: {request.url.path}")


@pytest.fixture()
def api(monkeypatch: pytest.MonkeyPatch) -> StubApi:
    stub = StubApi()

    # `chat_mod.httpx` IS the httpx module, so this patch is global for the
    # test — hence the real class is captured first. Patching in place without
    # it makes `build` call itself.
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


def _events(ws: Any, count: int) -> list[dict[str, Any]]:
    return [json.loads(ws.receive_text()) for _ in range(count)]


def _start(ws: Any, *, ticket: str = "t", resume_token: str | None = None) -> None:
    payload: dict[str, Any] = {"ticket": ticket, "conversation_id": "c1", "locale": "en"}
    if resume_token:
        payload["resume_token"] = resume_token
    ws.send_text(json.dumps({"type": "session.start", "seq": 0, "ts": 0, "payload": payload}))


def _say(ws: Any, text: str, seq: int = 1, cid: str = "m1") -> None:
    ws.send_text(
        json.dumps(
            {
                "type": "captions.final",
                "seq": seq,
                "ts": 0,
                "payload": {"role": "user", "text": text, "client_message_id": cid},
            }
        )
    )


# ---------------------------------------------------------------------------
# The protocol
# ---------------------------------------------------------------------------


def test_a_turn_speaks_only_the_closed_event_set(api: StubApi) -> None:
    """§34.6's set is closed at fifteen and this service invents none of it."""
    with TestClient(app).websocket_connect("/chat/session") as ws:
        _start(ws)
        ready = _events(ws, 1)[0]
        assert ready["type"] == ControlEventType.SESSION_READY.value

        _say(ws, "what is Saturn doing?")
        seen = _events(ws, len(api.stages) + 1)

    closed_set = {t.value for t in ControlEventType}
    assert all(e["type"] in closed_set for e in [ready, *seen])
    assert {e["type"] for e in seen} == {"presence.state", "captions.final"}


def test_presence_follows_the_real_pipeline_stages(api: StubApi) -> None:
    """§25.4's typing indicator, driven by §9 rather than by a timer.

    The stages come from the API's stream, which comes from the tracer, which
    sees every stage exactly once. A stage the map does not name emits nothing
    — asserted here so a future §9 stage cannot start animating a state
    nobody designed.
    """
    api.stages = ["language_detect", "safety_pre", "memory_retrieval", "generation"]
    with TestClient(app).websocket_connect("/chat/session") as ws:
        _start(ws)
        _events(ws, 1)
        _say(ws, "hello")
        seen = _events(ws, 4)

    presence = [e for e in seen if e["type"] == "presence.state"]
    assert [p["payload"]["state"] for p in presence] == [
        PresenceState.LISTENING.value,
        PresenceState.THOUGHTFUL.value,
        PresenceState.SPEAKING_SOFT.value,
    ]
    # `language_detect` is not in the map, so it produced nothing.
    assert len(presence) == 3


def test_tara_text_arrives_only_as_a_final_caption(api: StubApi) -> None:
    """**The fabrication gate, from this side.**

    There is no partial for Tara — not because a rule forbids it but because
    this service never holds a draft: the only thing it receives that carries
    her words is a validated `ChatTurn`. A `captions.partial` here would have
    to be invented out of nothing.
    """
    with TestClient(app).websocket_connect("/chat/session") as ws:
        _start(ws)
        _events(ws, 1)
        _say(ws, "what is Saturn doing?")
        seen = _events(ws, len(api.stages) + 1)

    assert not any(e["type"] == "captions.partial" for e in seen)
    final = [e for e in seen if e["type"] == "captions.final"]
    assert len(final) == 1
    assert final[0]["payload"]["role"] == "tara"
    assert final[0]["payload"]["turn"]["text"] == TURN["text"]

    # And nothing before it carried a word of her reply.
    for event in seen[:-1]:
        assert "Saturn" not in json.dumps(event)


def test_every_answer_acks_the_seq_it_answers(api: StubApi) -> None:
    """§34.6: "server acks control events by seq". There is no ack MEMBER, so
    it rides on the reply — which is why `ControlEvent.ack` exists."""
    with TestClient(app).websocket_connect("/chat/session") as ws:
        _start(ws)
        ready = _events(ws, 1)[0]
        _say(ws, "hello", seq=7)
        seen = _events(ws, len(api.stages) + 1)

    assert ready["ack"] == 0
    assert seen[-1]["ack"] == 7


def test_a_binary_frame_is_refused_until_m9(api: StubApi) -> None:
    """§33.1 is a storage question. A socket that quietly accepts PCM has
    opened it a milestone early."""
    with TestClient(app).websocket_connect("/chat/session") as ws:
        _start(ws)
        _events(ws, 1)
        ws.send_bytes(b"\x00" * 16)
        error = _events(ws, 1)[0]

    assert error["type"] == "error"
    assert error["payload"]["code"] == "SYS_VALIDATION"


def test_a_turn_before_the_handshake_is_refused(api: StubApi) -> None:
    with TestClient(app).websocket_connect("/chat/session") as ws:
        _say(ws, "let me in")
        error = _events(ws, 1)[0]

    assert error["type"] == "error"
    assert error["payload"]["code"] == "AUTH_INVALID_TOKEN"
    assert api.turn_calls == 0


def test_a_refused_ticket_closes_the_socket_with_an_envelope(api: StubApi) -> None:
    api.redeem_status = 401
    with TestClient(app).websocket_connect("/chat/session") as ws:
        _start(ws, ticket="stale")
        error = _events(ws, 1)[0]

    assert error["type"] == "error"
    assert error["payload"]["code"] == "AUTH_INVALID_TOKEN"


def test_a_pipeline_error_is_forwarded_as_the_canonical_envelope(api: StubApi) -> None:
    """§34.4: one envelope, never a custom shape — even three services deep."""
    api.fail = {"error": {"code": "SYS_UNAVAILABLE", "message_key": "errors.sys.unavailable"}}
    with TestClient(app).websocket_connect("/chat/session") as ws:
        _start(ws)
        _events(ws, 1)
        _say(ws, "hello")
        seen = _events(ws, len(api.stages) + 1)

    error = seen[-1]
    assert error["type"] == "error"
    assert set(error["payload"]) == {"code", "message_key", "trace_id", "retryable"}
    assert error["payload"]["retryable"] is True


# ---------------------------------------------------------------------------
# T2 — what happens when the socket drops mid-turn
# ---------------------------------------------------------------------------


def test_a_completed_turn_survives_the_socket_that_asked_for_it(api: StubApi) -> None:
    """The second test this milestone was specified around, server side.

    The pipeline answered; the socket was gone. The answer waits in the resume
    buffer for §34.6's five minutes rather than being thrown away — and rather
    than being re-run, which would charge the user twice for one question and
    could return different words to the same ones.
    """
    buffer = ResumeBuffer()
    buffer.put("tok", TURN, "m1")

    pending = buffer.take("tok")
    assert pending is not None
    assert pending.turn["text"] == TURN["text"]
    # Taken once. A second reconnect does not replay it into the thread.
    assert buffer.take("tok") is None


def test_a_reconnect_inside_the_window_is_offered_the_pending_turn(api: StubApi) -> None:
    """§32.11's one-tap resume, carrying the answer it already has."""
    app.state.resume_buffer.put("tok", TURN, "m1")

    with TestClient(app).websocket_connect("/chat/session") as ws:
        _start(ws, resume_token="tok")
        offer, ready = _events(ws, 2)

    assert offer["type"] == "resume.offer"
    assert offer["payload"]["pending_turn"]["text"] == TURN["text"]
    assert offer["payload"]["pending_client_message_id"] == "m1"
    assert ready["type"] == "session.ready"
    # The turn was NOT re-run to produce that offer.
    assert api.turn_calls == 0


def test_a_reconnect_after_the_window_is_offered_nothing(api: StubApi, monkeypatch) -> None:
    """Past five minutes §34.6 says the socket stops trying to resume. The
    client falls back to `POST /v1/chat/turn` with full context, which is what
    `handoff.to_text` tells it to do."""
    buffer = ResumeBuffer()
    buffer.put("tok", TURN, "m1")
    # Age the entry past the window rather than sleeping through it.
    buffer.pending["tok"].stored_at -= 10_000

    assert buffer.take("tok") is None

    app.state.resume_buffer = buffer
    with TestClient(app).websocket_connect("/chat/session") as ws:
        _start(ws, resume_token="tok")
        first = _events(ws, 1)[0]

    assert first["type"] == "session.ready"


def test_a_fresh_session_gets_a_resume_token_to_come_back_with(api: StubApi) -> None:
    with TestClient(app).websocket_connect("/chat/session") as ws:
        _start(ws)
        ready = _events(ws, 1)[0]

    assert ready["payload"]["resume_token"]
    assert ready["payload"]["resume_window_s"] == 300
    assert ready["payload"]["conversation_id"] == REDEEM["conversation_id"]


def test_a_second_question_mid_turn_is_refused_rather_than_interleaved(
    api: StubApi,
) -> None:
    """Two presence streams and two answers braided into one thread is worse
    than an honest "one at a time".

    The first turn is HELD open rather than raced against: a version of this
    test that merely sent two messages quickly passed for the wrong reason —
    the mock answered the first before the second was read, so the guard was
    never reached and the test asserted nothing.
    """
    api.stages = []
    with TestClient(app).websocket_connect("/chat/session") as ws:
        _start(ws)
        _events(ws, 1)

        api.hold = asyncio.Event()
        _say(ws, "first", seq=1, cid="m1")
        _say(ws, "second", seq=2, cid="m2")

        refusal = _events(ws, 1)[0]
        assert refusal["type"] == "error"
        assert refusal["payload"]["code"] == "SYS_RATE_LIMITED"
        assert refusal["ack"] == 2

        api.hold.set()
        answer = _events(ws, 1)[0]

    assert answer["type"] == "captions.final"
    assert answer["ack"] == 1
    assert answer["payload"]["client_message_id"] == "m1"
    assert api.turn_calls == 1
