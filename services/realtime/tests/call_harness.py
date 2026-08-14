"""The shared call-socket harness (M9-P10b).

Two test files drive `WS /call/session` — the degrade ladder and the barge-in —
and they need the same three things: a real browser-facing socket, a stubbed
ticket redemption, and a `sitara-api` media socket the test can drive frame by
frame. Those live here rather than in one of the two, so neither file owns the
other's setup.

**What is real and what is not, restated because it is the point.** The socket
the BROWSER speaks is real: `TestClient.websocket_connect` performs a real
upgrade and a real close, for the reason `apps/web/scripts/stub-realtime.mjs`
records at length — a suite that replaces the transport verifies frame handling
over a connection that was never opened. What is faked is the media socket to
`sitara-api`, at the client-object seam, exactly where `test_chat_socket.py`
fakes the API with `httpx.MockTransport`. The far side of that seam is exercised
for real in `services/api/tests/calls/`. Neither suite fakes both ends of one
hop.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx
import pytest
from sitara_schemas.call_media import CallDownFrame, CallUpFrame

from sitara_realtime import call as call_mod
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

SPOKEN = "what is Saturn doing today?"


class FakeMedia:
    """`sitara-api`'s media socket, driven by the test.

    It enforces the contract the real one enforces — `CallUpFrame` /
    `CallDownFrame` from `sitara_schemas.call_media`, never a string invented
    here — so a frame this accepts is a frame the real socket accepts. A fake
    that took a name the real side would ignore is the root CLAUDE.md defect,
    and on this socket it would look exactly like a working call.
    """

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.audio_bytes = 0
        self.closed = False
        self._inbox: asyncio.Queue[dict[str, Any] | bytes | None] = asyncio.Queue()
        #: The loop the app runs on. `TestClient` drives the app in a portal
        #: THREAD, so the test pushes frames from a different thread than the
        #: one awaiting them — and `Queue.put_nowait` across threads appends the
        #: item while the waiting getter's wakeup never gets scheduled, so the
        #: whole suite hangs rather than failing. Captured on the first
        #: iteration and used through `call_soon_threadsafe` below.
        self._loop: asyncio.AbstractEventLoop | None = None

    # -- what realtime sends us --------------------------------------------

    async def send(self, frame: dict[str, Any]) -> None:
        CallUpFrame(frame["type"])  # raises on anything not in the closed set
        self.sent.append(frame)

    async def send_audio(self, pcm: bytes) -> None:
        self.audio_bytes += len(pcm)

    async def aclose(self) -> None:
        self.closed = True
        await self._inbox.put(None)

    # -- what we send realtime ---------------------------------------------

    def push(self, kind: CallDownFrame, **payload: Any) -> None:
        self._offer({"type": kind.value, **payload})

    def push_audio(self, pcm: bytes) -> None:
        self._offer(pcm)

    def finish(self) -> None:
        self._offer(None)

    def _offer(self, item: dict[str, Any] | bytes | None) -> None:
        """Hand an item to the app's loop from the test's thread."""
        loop, deadline = None, time.monotonic() + 2.0
        while loop is None and time.monotonic() < deadline:
            loop = self._loop
            if loop is None:
                time.sleep(0.005)
        assert loop is not None, "the media pump never started"
        loop.call_soon_threadsafe(self._inbox.put_nowait, item)

    def __aiter__(self) -> Any:
        return self._events()

    async def _events(self) -> Any:
        self._loop = asyncio.get_running_loop()
        while True:
            item = await self._inbox.get()
            if item is None:
                return
            yield item

    def frames(self, kind: CallUpFrame) -> list[dict[str, Any]]:
        return [f for f in self.sent if f["type"] == kind.value]


def make_media_fixture(monkeypatch: pytest.MonkeyPatch) -> FakeMedia:
    """Wrapped into the `media` fixture by `conftest.py`."""
    fake = FakeMedia()

    async def open_media(*_args: object, **_kwargs: object) -> FakeMedia:
        return fake

    async def redeem_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/call/ws/redeem"
        return httpx.Response(200, json=REDEEM)

    real_client = httpx.AsyncClient

    def build(*_args: object, **kwargs: object) -> httpx.AsyncClient:
        return real_client(
            transport=httpx.MockTransport(redeem_handler),
            base_url=str(kwargs.get("base_url", "http://api")),
        )

    monkeypatch.setattr(call_mod, "open_media", open_media)
    monkeypatch.setattr(call_mod.httpx, "AsyncClient", build)
    app.state.settings = Settings(service_key="k", api_base_url="http://api")
    app.state.resume_buffer = ResumeBuffer()
    return fake


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _start(ws: Any, *, resume_token: str | None = None) -> None:
    payload: dict[str, Any] = {"ticket": "t", "conversation_id": "c1", "locale": "en"}
    if resume_token:
        payload["resume_token"] = resume_token
    ws.send_text(json.dumps({"type": "session.start", "seq": 0, "ts": 0, "payload": payload}))


#: A binary frame — Tara's audio — rendered as a pseudo-event so `_drain` can
#: report one sequence. It is NOT a control event and is deliberately not
#: spelled like one: `test_a_call_invents_no_control_event` compares the
#: sequence against §34.6's closed fifteen, and a made-up member hiding in the
#: test's own vocabulary would make that assertion pass by accident.
AUDIO = "«audio»"


def _drain(ws: Any, *, until: str, limit: int = 40) -> list[dict[str, Any]]:
    """Read until `until` arrives, keeping binary and text in ONE sequence.

    Reading a fixed COUNT hides an ordering bug — the frames all still appear,
    just in the wrong order, and an assertion that only counted passes. Ordering
    is most of what this file tests, and the audio has to be in the same
    sequence as the events for "her words before her voice" to be checkable at
    all.
    """
    seen: list[dict[str, Any]] = []
    for _ in range(limit):
        message = ws.receive()
        if message.get("bytes") is not None:
            seen.append({"type": AUDIO, "payload": {"byte_length": len(message["bytes"])}})
            continue
        text = message.get("text")
        if text is None:
            raise AssertionError(f"socket closed before {until}: {message}")
        event = json.loads(text)
        seen.append(event)
        if event["type"] == until:
            return seen
    raise AssertionError(f"never saw {until}; got {[e['type'] for e in seen]}")


def _speak(media: FakeMedia, text: str = SPOKEN) -> None:
    """One finalised user utterance, as the recogniser delivers it."""
    media.push(CallDownFrame.CAPTION, text=text[:12], is_final=False)
    media.push(CallDownFrame.CAPTION, text=text, is_final=True)


def _types(events: list[dict[str, Any]]) -> list[str]:
    return [e["type"] for e in events]
