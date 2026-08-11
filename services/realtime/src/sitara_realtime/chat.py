"""The §34.6 chat socket, over the real §9 pipeline.

Everything this module sends is one of §34.6's fifteen control-event types,
imported from `sitara_schemas`. It invents nothing: the set is closed, and
additions are §31.3 change control in `packages/schemas`.

A text conversation in fifteen voice-shaped members
---------------------------------------------------

§34.6 is ONE protocol for voice notes, live calls and the chat socket, so a
typed conversation has to be said in members that already exist. It can be,
because a typed message is the same event a spoken one produces once STT has
run: a finalised caption. The mapping is written down in
`packages/schemas/src/ws-events.json` so both services read one description.

**`captions.partial` is never emitted for Tara, and that is the fabrication
gate.** §9 puts grounding, language-quality and safety-post AFTER generation.
Streaming tokens would race all three to the user's screen. This service is
built so it cannot: it never holds a draft. It calls `/v1/chat/ws/turn`, which
streams STAGE NAMES and then one validated `ChatTurn` — there is no frame in
that protocol carrying pre-validation text, so there is no expression here that
could forward one. The guarantee is the shape of the thing, not a rule someone
has to keep.

**Heartbeat is the transport's own ping/pong**, which is why §34.6's closed set
has no heartbeat member. Reap at 30s of silence (§29.2).

**A completed turn is buffered, not re-run.** §34.6 gives a 5-minute resume
window and §32.11 makes it a one-tap offer. If the socket drops after the
pipeline has answered, re-running the turn on reconnect would charge the user
twice for one question and could return a different answer to the same words.
So the answer waits, and `resume.offer` carries it.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from fastapi import WebSocket, WebSocketDisconnect
from sitara_schemas import (
    HEARTBEAT_INTERVAL_S,
    REAP_AFTER_SILENCE_S,
    RESUME_WINDOW_S,
    ControlEvent,
    ControlEventType,
    PresenceState,
)

from sitara_realtime.config import Settings

logger = logging.getLogger(__name__)

#: §9's stages → §4.3's presence states.
#:
#: This is the whole of "typing/presence driven by real pipeline stage events".
#: A stage the map does not name emits NOTHING — deliberately. §25.4 asks for
#: "Tara is typing…" and "Tara is listening…", not for an indicator that
#: animates through every internal step; and a stage list that grows in M9
#: must not start emitting presence changes nobody designed.
STAGE_PRESENCE: dict[str, PresenceState] = {
    # She has the message and is working out what it needs.
    "safety_pre": PresenceState.LISTENING,
    "intent": PresenceState.LISTENING,
    # Gathering: memory, then facts. This is the long part of a real turn.
    "memory_retrieval": PresenceState.THOUGHTFUL,
    "fact_tools": PresenceState.THOUGHTFUL,
    # Writing.
    "generation": PresenceState.SPEAKING_SOFT,
}


@dataclass
class PendingTurn:
    """A turn that completed while nobody was listening (§32.11)."""

    turn: dict[str, Any]
    client_message_id: str
    stored_at: float


@dataclass
class ResumeBuffer:
    """In-process, and that is a stated limitation rather than an oversight.

    §6.1 gives WS sessions sticky routing, so a reconnect inside five minutes
    lands on the same instance in the normal case. A redeploy loses the buffer,
    and the honest consequence is `handoff.to_text` — the thread continues over
    `POST /v1/chat/turn` with full context, which is exactly what §34.6
    prescribes when a resume is not possible. Moving this to Redis is a
    scaling decision for when the losses are measured, not a correctness one.
    """

    pending: dict[str, PendingTurn] = field(default_factory=dict)

    def put(self, token: str, turn: dict[str, Any], client_message_id: str) -> None:
        self.pending[token] = PendingTurn(turn, client_message_id, time.monotonic())

    def take(self, token: str) -> PendingTurn | None:
        entry = self.pending.pop(token, None)
        if entry is None:
            return None
        if time.monotonic() - entry.stored_at > RESUME_WINDOW_S:
            return None
        return entry

    def sweep(self) -> None:
        now = time.monotonic()
        for token in [
            t for t, e in self.pending.items() if now - e.stored_at > RESUME_WINDOW_S
        ]:
            self.pending.pop(token, None)


class ChatSession:
    """One socket, from `session.start` to close."""

    def __init__(
        self, ws: WebSocket, settings: Settings, buffer: ResumeBuffer
    ) -> None:
        self._ws = ws
        self._settings = settings
        self._buffer = buffer
        self._seq = 0
        self._ws_session: str | None = None
        self._resume_token: str | None = None
        self._conversation_id: str = ""

    # -- sending -----------------------------------------------------------

    async def send(
        self,
        type_: ControlEventType,
        payload: dict[str, Any],
        *,
        ack: int | None = None,
    ) -> None:
        event = ControlEvent(
            type=type_,
            seq=self._seq,
            ts=time.time() * 1000,
            ack=ack,
            payload=payload,
        )
        self._seq += 1
        await self._ws.send_text(event.model_dump_json())

    async def send_error(
        self, code: str, message_key: str, *, ack: int | None = None
    ) -> None:
        """§34.4's envelope, forwarded whole. `trace_id` is empty when the
        failure happened before the API could mint one — an invented id is
        worse than an absent one, because someone will search for it."""
        await self.send(
            ControlEventType.ERROR,
            {
                "code": code,
                "message_key": message_key,
                "trace_id": "",
                "retryable": code in ("SYS_UNAVAILABLE", "SYS_INTERNAL", "SYS_RATE_LIMITED"),
            },
            ack=ack,
        )

    # -- the turn ----------------------------------------------------------

    async def run_turn(
        self, text: str, client_message_id: str, quoted: str | None, ack: int
    ) -> None:
        assert self._ws_session is not None
        turn: dict[str, Any] | None = None
        failed: tuple[str, str] | None = None

        try:
            async with httpx.AsyncClient(
                base_url=self._settings.api_base_url,
                timeout=self._settings.api_timeout_seconds,
            ) as client:
                async with client.stream(
                    "POST",
                    "/v1/chat/ws/turn",
                    json={"text": text, "quoted_message_id": quoted},
                    headers={
                        "X-Sitara-Service-Key": self._settings.service_key or "",
                        "X-Sitara-WS-Session": self._ws_session,
                    },
                ) as response:
                    if response.status_code >= 400:
                        body = await response.aread()
                        failed = _envelope_from(body)
                    else:
                        async for line in response.aiter_lines():
                            if not line.strip():
                                continue
                            frame = json.loads(line)
                            if "stage" in frame:
                                await self._presence_for(frame["stage"])
                            elif "turn" in frame:
                                turn = frame["turn"]
                            elif "error" in frame:
                                failed = (
                                    frame["error"]["code"],
                                    frame["error"]["message_key"],
                                )
        except (httpx.HTTPError, json.JSONDecodeError):
            logger.exception("ws turn call failed")
            failed = ("SYS_UNAVAILABLE", "errors.sys.unavailable")

        if turn is not None:
            # Buffered BEFORE the send. If the socket died between the
            # pipeline answering and this line, a reconnect must still find the
            # answer — buffering after a successful send would lose exactly the
            # turns the resume window exists for.
            if self._resume_token:
                self._buffer.put(self._resume_token, turn, client_message_id)
            await self.send(
                ControlEventType.CAPTIONS_FINAL,
                {"role": "tara", "client_message_id": client_message_id, "turn": turn},
                ack=ack,
            )
            return

        code, key = failed or ("SYS_INTERNAL", "errors.sys.internal")
        await self.send_error(code, key, ack=ack)

    async def _presence_for(self, stage: str) -> None:
        state = STAGE_PRESENCE.get(stage)
        if state is None:
            return
        await self.send(
            ControlEventType.PRESENCE_STATE,
            {"state": state.value, "stage": stage},
        )

    # -- the handshake -----------------------------------------------------

    async def start(self, payload: dict[str, Any], ack: int) -> bool:
        ticket = payload.get("ticket")
        if not isinstance(ticket, str) or not ticket:
            await self.send_error("AUTH_INVALID_TOKEN", "errors.auth.invalid_token", ack=ack)
            return False

        try:
            async with httpx.AsyncClient(
                base_url=self._settings.api_base_url,
                timeout=self._settings.api_timeout_seconds,
            ) as client:
                response = await client.post(
                    "/v1/chat/ws/redeem",
                    json={"ticket": ticket},
                    headers={"X-Sitara-Service-Key": self._settings.service_key or ""},
                )
        except httpx.HTTPError:
            logger.exception("ticket redemption failed")
            await self.send_error("SYS_UNAVAILABLE", "errors.sys.unavailable", ack=ack)
            return False

        if response.status_code >= 400:
            code, key = _envelope_from(response.content)
            await self.send_error(code, key, ack=ack)
            return False

        grant = response.json()
        self._ws_session = grant["ws_session"]
        self._conversation_id = grant["conversation_id"]

        # A reconnect presenting last session's token gets its answer back
        # rather than its question re-asked (§32.11).
        offered = payload.get("resume_token")
        if isinstance(offered, str) and offered:
            pending = self._buffer.take(offered)
            if pending is not None:
                await self.send(
                    ControlEventType.RESUME_OFFER,
                    {
                        "conversation_id": self._conversation_id,
                        "pending_turn": pending.turn,
                        "pending_client_message_id": pending.client_message_id,
                    },
                    ack=ack,
                )

        self._resume_token = secrets.token_urlsafe(24)
        await self.send(
            ControlEventType.SESSION_READY,
            {
                "resume_token": self._resume_token,
                "resume_window_s": RESUME_WINDOW_S,
                "conversation_id": self._conversation_id,
            },
            ack=ack,
        )
        return True

    @property
    def started(self) -> bool:
        return self._ws_session is not None


def _envelope_from(body: bytes) -> tuple[str, str]:
    """Read a §34.4 envelope out of a response, or say so honestly.

    A proxy error or a 502 has no envelope in it. Inventing a code would send
    the client a designed state for a failure that did not happen.
    """
    try:
        parsed = json.loads(body)
        return str(parsed["code"]), str(parsed["message_key"])
    except (json.JSONDecodeError, KeyError, TypeError):
        return "SYS_UNAVAILABLE", "errors.sys.unavailable"


async def chat_socket(ws: WebSocket, settings: Settings, buffer: ResumeBuffer) -> None:
    """`WS /chat/session`. Binary frames are refused until M9."""
    await ws.accept()
    session = ChatSession(ws, settings, buffer)
    buffer.sweep()
    last_seen = time.monotonic()
    turn_task: asyncio.Task[None] | None = None

    async def heartbeat() -> None:
        """§34.6: ping every 10s, reap at 30s of silence (§29.2).

        The transport's own ping, not a JSON event — which is exactly why the
        closed set has no heartbeat member to invent.
        """
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL_S)
            if time.monotonic() - last_seen > REAP_AFTER_SILENCE_S:
                logger.info("reaping a silent chat socket")
                await ws.close(code=1001)
                return

    beat = asyncio.create_task(heartbeat())
    try:
        while True:
            message = await ws.receive()
            last_seen = time.monotonic()

            if message["type"] == "websocket.disconnect":
                break
            if message.get("bytes") is not None:
                # §33.1 is a storage question and M9 is where it gets answered.
                # A socket that quietly accepts PCM has opened it early.
                await session.send_error("SYS_VALIDATION", "errors.sys.validation")
                continue

            raw = message.get("text")
            if not raw:
                continue
            try:
                event = ControlEvent.model_validate_json(raw)
            except ValueError:
                await session.send_error("SYS_VALIDATION", "errors.sys.validation")
                continue

            if event.type is ControlEventType.SESSION_START:
                if not await session.start(event.payload, event.seq):
                    break
                continue

            if not session.started:
                await session.send_error(
                    "AUTH_INVALID_TOKEN", "errors.auth.invalid_token", ack=event.seq
                )
                continue

            if event.type is ControlEventType.SESSION_END:
                break

            if event.type is ControlEventType.CAPTIONS_FINAL:
                payload = event.payload
                text = payload.get("text")
                if payload.get("role") != "user" or not isinstance(text, str) or not text.strip():
                    await session.send_error(
                        "SYS_VALIDATION", "errors.sys.validation", ack=event.seq
                    )
                    continue
                if turn_task is not None and not turn_task.done():
                    # One turn at a time. A second question while the first is
                    # in flight would interleave two presence streams and two
                    # answers into one thread.
                    await session.send_error(
                        "SYS_RATE_LIMITED", "errors.sys.rate_limited", ack=event.seq
                    )
                    continue
                turn_task = asyncio.create_task(
                    session.run_turn(
                        text,
                        str(payload.get("client_message_id") or ""),
                        payload.get("quoted_message_id"),
                        event.seq,
                    )
                )
                continue

            # Every other member of the closed set belongs to voice (M9). It is
            # not an error for a client to send one; it is simply not answered
            # yet, and saying so is more useful than silence.
            logger.info("control event not handled by the text chat", extra={"type": event.type})
    except WebSocketDisconnect:
        pass
    finally:
        beat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await beat
        if turn_task is not None and not turn_task.done():
            # The turn keeps running: it will land in the resume buffer, which
            # is what makes a mid-turn drop recoverable rather than a repeat.
            with contextlib.suppress(Exception):
                await asyncio.wait_for(turn_task, timeout=settings.api_timeout_seconds)
