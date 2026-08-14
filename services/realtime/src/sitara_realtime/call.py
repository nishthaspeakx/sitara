"""`WS /call/session` — §25.3's live call, in §34.6's fifteen members.

What this service owns, and what it deliberately does not
---------------------------------------------------------

§25.7 puts the call-session service here: the state machine, server-side VAD
and ducking for barge-in, per-session minute metering, and the degrade ladder.
Everything else is `sitara-api`'s, reached over the media socket
(`sitara_schemas.call_media`), because this service holds no database, no model
client and no vendor credentials — an invariant M10 does not weaken. So:

    here                                  there
    ────                                  ─────
    §34.6 protocol, seq, heartbeat        the §9 pipeline
    server-side VAD, barge-in             Ink / Sonic, over their sockets
    the session CLOCK                     the minute QUOTA (§7.3)
    the degrade ladder (§25.3, §8)        the transcript, committed to Mongo
    the resume window (§32.11)            §33.5's evidence, stored

The one rule the whole file is arranged around
-----------------------------------------------

**A dropped call must never lose what was said.** Call audio is never stored
(§13, §33.1), so a spoken sentence has no recording to fall back on and no
composer to resend from — if the transcript is not already in the thread when
something fails, the words are gone. The API commits it the moment STT
finalises, before §9 runs; this side's job is to make every failure end
somewhere designed rather than in silence, and to say the same true sentence
about it each time: the conversation continues in messages, and everything you
both said is in it.

That is why every branch of `_degrade` ends in `handoff.to_text` and none of
them ends in a bare close.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
import websockets
from fastapi import WebSocket, WebSocketDisconnect
from sitara_schemas import (
    BINARY_HEADER_BYTES,
    BINARY_SAMPLE_RATE_HZ,
    HEARTBEAT_INTERVAL_S,
    REAP_AFTER_SILENCE_S,
    RESUME_WINDOW_S,
    BargeInReason,
    ControlEvent,
    ControlEventType,
    PlaybackPolicy,
    PresenceState,
    TranscriptStatus,
    VadState,
)
from sitara_schemas.call_media import CALL_TICK_INTERVAL_S, CallDownFrame, CallUpFrame

from sitara_realtime.chat import STAGE_PRESENCE, ResumeBuffer, _envelope_from
from sitara_realtime.config import Settings
from sitara_realtime.vad import SpeechDetector

logger = logging.getLogger(__name__)

#: 16 kHz mono s16le. Used to turn byte counts into seconds for §33.5's
#: latency measure and for the cost inputs.
BYTES_PER_SECOND = BINARY_SAMPLE_RATE_HZ * 2


class MediaClient(Protocol):
    """`sitara-api`'s media socket. See `packages/schemas/src/call-media.json`."""

    async def send(self, frame: dict[str, Any]) -> None: ...
    async def send_audio(self, pcm: bytes) -> None: ...
    def __aiter__(self) -> Any: ...
    async def aclose(self) -> None: ...


class WebSocketMediaClient:
    """The real one. A websocket because the channel is duplex for the whole
    call — a voice note fitted request/response and a call does not."""

    def __init__(self, connection: Any) -> None:
        self._ws = connection

    async def send(self, frame: dict[str, Any]) -> None:
        await self._ws.send(json.dumps(frame))

    async def send_audio(self, pcm: bytes) -> None:
        await self._ws.send(pcm)

    def __aiter__(self) -> Any:
        return self._events()

    async def _events(self) -> Any:
        async for message in self._ws:
            if isinstance(message, bytes):
                yield message
                continue
            try:
                yield json.loads(message)
            except json.JSONDecodeError:
                continue

    async def aclose(self) -> None:
        with contextlib.suppress(Exception):
            await self._ws.close()


async def open_media(settings: Settings, ws_session: str) -> MediaClient:
    """Module-level so a test can substitute it, exactly as `chat.py`'s tests
    substitute `httpx.AsyncClient`. The socket the BROWSER speaks stays real in
    both suites; what gets substituted is one hop further in, and the far side
    of that hop has its own real-socket test in `services/api`."""
    url = settings.api_base_url.replace("http://", "ws://").replace("https://", "wss://")
    connection = await websockets.connect(
        f"{url.rstrip('/')}/v1/call/media",
        additional_headers={
            "X-Sitara-Service-Key": settings.service_key or "",
            "X-Sitara-WS-Session": ws_session,
        },
    )
    return WebSocketMediaClient(connection)


@dataclass
class Utterance:
    """One thing the user said, from the first interim caption to its answer."""

    client_message_id: str
    text: str = ""
    #: When the final transcript landed. §33.5's first-response measure runs
    #: from HERE to the first byte of audio — end to end as the user waits,
    #: not the vendor's TTFB, which excludes §9 entirely and would report a
    #: number nobody has ever waited.
    finalised_at: float | None = None
    first_audio_reported: bool = False
    chunk_seq: int = 0
    #: Bytes of her audio this service actually put on the browser's socket.
    #: `tts.end`'s duration is computed from this and not from the API's chunk
    #: count, so the scrubber describes what arrived.
    sent_audio_bytes: int = 0


class CallSession:
    """One socket, from `session.start` to the handoff or the goodbye."""

    def __init__(self, ws: WebSocket, settings: Settings, buffer: ResumeBuffer) -> None:
        self._ws = ws
        self._settings = settings
        self._buffer = buffer
        self._seq = 0
        self._ws_session: str | None = None
        self._resume_token: str | None = None
        self._conversation_id = ""
        self._locale = "en"
        self._media: MediaClient | None = None
        self._detector = SpeechDetector()
        self._speaking = False
        self._utterance: Utterance | None = None
        self._started_at = 0.0
        self._metered_seconds = 0.0
        #: The handoff has been sent; no further §34.6 event may follow it.
        #: **Deliberately distinct from `_degraded`.** An earlier version used
        #: one flag, set it before writing the handoff, and `send` then
        #: suppressed the one frame the whole ladder exists to deliver — the
        #: call simply went quiet and was reaped 30 seconds later. Idempotency
        #: and silence are two different questions and they need two answers.
        self._closed = False
        #: `_degrade` has run. Guards against a second ladder entry — a TTS
        #: failure and a media-socket loss arrive together often enough that
        #: this is the normal case, not an edge one.
        self._degraded = False

    # -- sending -----------------------------------------------------------

    async def send(
        self, type_: ControlEventType, payload: dict[str, Any], *, ack: int | None = None
    ) -> None:
        if self._closed:
            return
        event = ControlEvent(
            type=type_, seq=self._seq, ts=time.time() * 1000, ack=ack, payload=payload
        )
        self._seq += 1
        with contextlib.suppress(Exception):
            await self._ws.send_text(event.model_dump_json())

    async def send_error(self, code: str, message_key: str) -> None:
        await self.send(
            ControlEventType.ERROR,
            {
                "code": code,
                "message_key": message_key,
                "trace_id": "",
                "retryable": code in ("SYS_UNAVAILABLE", "SYS_INTERNAL", "SYS_RATE_LIMITED"),
            },
        )

    async def report(self, observation: str, *, value: float = 1.0) -> None:
        """§33.5's evidence. This service has no database, so it says what it
        saw and `sitara-api` records it (§43.5)."""
        if self._media is None:
            return
        with contextlib.suppress(Exception):
            await self._media.send(
                {
                    "type": CallUpFrame.METRIC.value,
                    "observation": observation,
                    "value": value,
                    "locale": self._locale,
                }
            )

    # -- the handshake -----------------------------------------------------

    async def start(self, payload: dict[str, Any], ack: int) -> bool:
        ticket = payload.get("ticket")
        if not isinstance(ticket, str) or not ticket:
            await self.send_error("AUTH_INVALID_TOKEN", "errors.auth.invalid_token")
            return False

        try:
            async with httpx.AsyncClient(
                base_url=self._settings.api_base_url,
                timeout=self._settings.api_timeout_seconds,
            ) as client:
                response = await client.post(
                    "/v1/call/ws/redeem",
                    json={"ticket": ticket},
                    headers={"X-Sitara-Service-Key": self._settings.service_key or ""},
                )
        except httpx.HTTPError:
            logger.exception("call ticket redemption failed")
            await self.send_error("SYS_UNAVAILABLE", "errors.sys.unavailable")
            return False

        if response.status_code >= 400:
            code, key = _envelope_from(response.content)
            await self.send_error(code, key)
            return False

        grant = response.json()
        self._ws_session = grant["ws_session"]
        self._conversation_id = grant["conversation_id"]
        self._locale = grant.get("locale") or "en"

        # §32.11 — a reconnect presenting last session's token gets the answer
        # it never heard, rather than being asked to say it all again.
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

        try:
            self._media = await open_media(self._settings, str(self._ws_session))
        except Exception:
            logger.exception("call media socket refused")
            await self.send_error("SYS_UNAVAILABLE", "errors.sys.unavailable")
            return False

        self._resume_token = secrets.token_urlsafe(24)
        self._started_at = time.monotonic()
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

    # -- microphone in -----------------------------------------------------

    async def on_audio(self, frame: bytes) -> None:
        """One §34.6 binary frame from the browser.

        **A sequence gap does not fail a call**, and that is the one place this
        deliberately differs from `chat.Recording`. A voice NOTE with a hole in
        it still transcribes, into a fluent sentence the user never said, which
        reaches §9 as their question — so a note dies on a gap. A live call's
        lost packet is a lost moment: the recogniser hears a clip, the user
        hears themselves being misunderstood, and they say it again. Killing the
        call would turn a bad second into a lost conversation.
        """
        if self._media is None or len(frame) < BINARY_HEADER_BYTES:
            return
        pcm = frame[BINARY_HEADER_BYTES:]

        # §25.3's ducking. The detector runs on every frame, but only the
        # transition into speech WHILE SHE IS SPEAKING is a barge-in.
        was_speaking = self._detector.speaking
        speaking_now = self._detector.feed(pcm)
        if speaking_now and not was_speaking:
            await self._on_speech_start()
        elif was_speaking and not speaking_now:
            await self.send(
                ControlEventType.VAD_STATE,
                {
                    "state": VadState.SPEECH_END.value,
                    "client_message_id": self._utterance.client_message_id
                    if self._utterance
                    else "",
                },
            )

        with contextlib.suppress(Exception):
            await self._media.send_audio(pcm)

    async def _on_speech_start(self) -> None:
        if self._utterance is None:
            # §34.6's `$m10_is_the_same_protocol`: in a call the SERVER mints
            # the id, because server-side VAD is what opened the bracket.
            self._utterance = Utterance(client_message_id=f"u{secrets.token_hex(6)}")
        await self.send(
            ControlEventType.VAD_STATE,
            {
                "state": VadState.SPEECH_START.value,
                "client_message_id": self._utterance.client_message_id,
            },
        )
        if not self._speaking or self._media is None:
            return
        # She is talking and so are they. §7.3: one in-flight utterance max.
        await self.report("barge_in_attempt")
        with contextlib.suppress(Exception):
            await self._media.send({"type": CallUpFrame.CANCEL_SPEECH.value})

    # -- media in ----------------------------------------------------------

    async def pump_media(self) -> None:
        assert self._media is not None
        try:
            async for item in self._media:
                if isinstance(item, bytes):
                    await self._on_tts_audio(item)
                    continue
                await self._on_media_frame(item)
        except Exception:
            logger.exception("call media socket lost")
            await self._degrade("media_socket_lost")

    async def _on_media_frame(self, frame: dict[str, Any]) -> None:
        kind = frame.get("type")

        if kind == CallDownFrame.CAPTION.value:
            await self._on_caption(str(frame.get("text") or ""), bool(frame.get("is_final")))
            return

        if kind == CallDownFrame.STAGE.value:
            state = STAGE_PRESENCE.get(str(frame.get("stage")))
            if state is not None:
                await self.send(
                    ControlEventType.PRESENCE_STATE,
                    {"state": state.value, "stage": frame.get("stage")},
                )
            return

        if kind == CallDownFrame.TURN.value:
            await self._on_turn(frame)
            return

        if kind == CallDownFrame.TTS_START.value:
            self._speaking = True
            await self.send(
                ControlEventType.TTS_START,
                {
                    "client_message_id": frame.get("client_message_id"),
                    # Null, and the null is the point: a call's audio is
                    # streamed and never stored (§33.1), so there is no asset
                    # and nothing to replay. An invented id here would promise
                    # a playback control over audio that exists nowhere.
                    "tts_audio_asset_id": None,
                    "sample_rate_hz": frame.get("sample_rate_hz", BINARY_SAMPLE_RATE_HZ),
                    "voice_id": None,
                },
            )
            await self.send(
                ControlEventType.PRESENCE_STATE,
                {"state": PresenceState.SPEAKING_SOFT.value, "stage": None},
            )
            return

        if kind == CallDownFrame.TTS_END.value:
            self._speaking = False
            chunks = int(frame.get("chunks") or 0)
            await self.send(
                ControlEventType.TTS_END,
                {
                    "client_message_id": frame.get("client_message_id"),
                    "duration_ms": self._duration_ms(chunks),
                },
            )
            self._utterance = None
            return

        if kind == CallDownFrame.TTS_CANCELLED.value:
            await self._on_tts_cancelled(frame)
            return

        if kind == CallDownFrame.ENTITLEMENT_WARNING.value:
            # §32.9's two notices, decided where the quota is. This side does
            # not re-derive them — one implementation of "once each".
            await self.send(
                ControlEventType.ENTITLEMENT_WARNING,
                {
                    "minutes_left": frame.get("minutes_left"),
                    "minutes_quota": frame.get("minutes_quota"),
                    "plan": frame.get("plan"),
                    "message_key": frame.get("message_key"),
                },
            )
            return

        if kind == CallDownFrame.EXHAUSTED.value:
            await self._degrade("entitlement_exhausted")
            return

        if kind == CallDownFrame.ERROR.value:
            await self.send_error(
                str(frame.get("code") or "SYS_INTERNAL"),
                str(frame.get("message_key") or "errors.sys.internal"),
            )
            # A turn that failed is different from a recogniser that died, and
            # the thread should say something true about which. The API tags
            # the envelope with the utterance it belongs to when there is one.
            await self._degrade(
                "turn_failed" if frame.get("client_message_id") else "stt_provider_failed"
            )
            return

    async def _on_caption(self, text: str, is_final: bool) -> None:
        if not text.strip():
            return
        if self._utterance is None:
            self._utterance = Utterance(client_message_id=f"u{secrets.token_hex(6)}")

        if not is_final:
            # §25.3's live captions. `role` is the constant `user` in the type,
            # which is what lets a caption be live without racing §9.
            await self.send(
                ControlEventType.CAPTIONS_PARTIAL,
                {
                    "role": "user",
                    "text": text,
                    "client_message_id": self._utterance.client_message_id,
                },
            )
            return

        self._utterance.text = text
        self._utterance.finalised_at = time.monotonic()
        await self.send(
            ControlEventType.CAPTIONS_FINAL,
            {
                "role": "user",
                "text": text,
                "client_message_id": self._utterance.client_message_id,
                "quoted_message_id": None,
                "transcript_status": TranscriptStatus.READY.value,
                # Spoken, and never stored (§13/§33.1). `text_only` would say
                # they typed it; `transcript_only` is the honest member.
                "playback_policy": PlaybackPolicy.TRANSCRIPT_ONLY.value,
                "source_audio_asset_id": None,
                "duration_ms": None,
                "source_audio_expires_at": None,
            },
        )
        if self._media is not None:
            with contextlib.suppress(Exception):
                await self._media.send(
                    {
                        "type": CallUpFrame.UTTERANCE.value,
                        "text": text,
                        "client_message_id": self._utterance.client_message_id,
                    }
                )

    async def _on_turn(self, frame: dict[str, Any]) -> None:
        turn = frame.get("turn")
        client_message_id = str(frame.get("client_message_id") or "")
        if self._utterance is not None and not client_message_id:
            client_message_id = self._utterance.client_message_id
        # Buffered BEFORE the send (§32.11), for the same reason the chat
        # buffers before sending: a socket that died between the pipeline
        # answering and this frame leaving must still find the answer on
        # reconnect, and buffering after a successful send loses exactly the
        # turns the window exists for.
        if self._resume_token and isinstance(turn, dict):
            self._buffer.put(self._resume_token, turn, client_message_id)
        await self.send(
            ControlEventType.CAPTIONS_FINAL,
            {"role": "tara", "client_message_id": client_message_id, "turn": turn},
        )

    async def _on_tts_audio(self, pcm: bytes) -> None:
        if self._utterance is not None and not self._utterance.first_audio_reported:
            self._utterance.first_audio_reported = True
            if self._utterance.finalised_at is not None:
                await self.report(
                    "first_audio_seconds",
                    value=time.monotonic() - self._utterance.finalised_at,
                )
        with contextlib.suppress(Exception):
            await self._ws.send_bytes(pcm)
        if self._utterance is None:
            return
        self._utterance.sent_audio_bytes += len(pcm)
        # §13: shapes, never content. No transcript rides beside the audio —
        # the words already crossed on `captions.final`.
        await self.send(
            ControlEventType.TTS_CHUNK_META,
            {
                "client_message_id": self._utterance.client_message_id,
                "seq": self._utterance.chunk_seq,
                "byte_length": len(pcm),
            },
        )
        self._utterance.chunk_seq += 1

    async def _on_tts_cancelled(self, frame: dict[str, Any]) -> None:
        self._speaking = False
        reason = str(frame.get("reason") or BargeInReason.USER_SPEECH.value)
        await self.send(
            ControlEventType.BARGE_IN,
            {
                "cancelled_client_message_id": frame.get("client_message_id"),
                "cancelled_after_chunk_seq": frame.get("after_chunk_seq"),
                "reason": reason,
            },
        )
        if reason == BargeInReason.USER_SPEECH.value:
            # §33.5's barge-in measure: the attempt was reported when we asked;
            # this is the confirmation that the stream actually stopped.
            await self.report("barge_in_stopped")
            self._detector.reset()
            self._utterance = None
            return
        if reason == BargeInReason.PROVIDER_FAILED.value:
            # §8's ladder: voice fails, text continues. Her words are already on
            # screen — they crossed before a single byte of audio — so this is
            # a call becoming a chat, not an answer being lost.
            await self._degrade("tts_provider_failed")

    # -- the ladder --------------------------------------------------------

    async def _degrade(self, reason: str) -> None:
        """§25.3's every-failure destination, and it is always the same place.

        `handoff.to_text` names the conversation, and the conversation already
        holds every word of the call: the API commits each transcript as STT
        finalises it and each of Tara's turns as §9 validates it. Nothing about
        the continuity travels on this frame, because nothing needs to — the
        thread IS the context, which is what makes "full transcript continuity"
        a property of where the words are rather than a promise about a payload.
        """
        if self._degraded:
            return
        self._degraded = True
        await self.report("recovery_attempt")
        await self.send(
            ControlEventType.HANDOFF_TO_TEXT,
            {"conversation_id": self._conversation_id, "reason": reason},
        )
        # Only now: the handoff is the LAST event, not a frame sent after the
        # socket was already declared shut.
        self._closed = True
        # Reported after the frame is on the wire: §33.5 counts a handoff that
        # actually reached the user, not one this service intended.
        await self.report("recovery_succeeded")
        await self._finish()

    async def _finish(self) -> None:
        if self._media is None:
            return
        self._metered_seconds = max(0.0, time.monotonic() - self._started_at)
        with contextlib.suppress(Exception):
            await self._media.send(
                {"type": CallUpFrame.END.value, "seconds": self._metered_seconds}
            )
        with contextlib.suppress(Exception):
            await self._media.aclose()
        self._media = None

    # -- metering ----------------------------------------------------------

    async def tick(self) -> None:
        """§32.9's heartbeat. The clock is here, the quota is there."""
        if self._media is None:
            return
        elapsed = max(0.0, time.monotonic() - self._started_at)
        with contextlib.suppress(Exception):
            await self._media.send({"type": CallUpFrame.TICK.value, "seconds": elapsed})

    def _duration_ms(self, chunks: int) -> int:
        """How long her reply actually was, from the bytes that actually left.

        Derived from `sent_audio_bytes` rather than from the API's chunk count
        or a vendor's claim about the utterance: §34.6's `tts.end` carries this
        for the scrubber, and a scrubber has to match the audio the client
        received. The two agree on a healthy call and diverge on exactly the
        call worth being honest about — one where the last chunks never made it.
        """
        del chunks
        if self._utterance is None:
            return 0
        return int(self._utterance.sent_audio_bytes / BYTES_PER_SECOND * 1000)

    @property
    def utterance(self) -> Utterance | None:
        return self._utterance


async def call_socket(ws: WebSocket, settings: Settings, buffer: ResumeBuffer) -> None:
    """`WS /call/session`."""
    await ws.accept()
    session = CallSession(ws, settings, buffer)
    buffer.sweep()
    last_seen = time.monotonic()
    pumps: list[asyncio.Task[None]] = []

    async def heartbeat() -> None:
        """§34.6: 10s, reap at 30s of silence (§29.2). The transport's own ping,
        which is why the closed set has no heartbeat member to invent."""
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL_S)
            if time.monotonic() - last_seen > REAP_AFTER_SILENCE_S:
                logger.info("reaping a silent call socket")
                await ws.close(code=1001)
                return

    async def metering() -> None:
        while True:
            await asyncio.sleep(CALL_TICK_INTERVAL_S)
            await session.tick()

    beat = asyncio.create_task(heartbeat())
    meter = asyncio.create_task(metering())
    try:
        while True:
            message = await ws.receive()
            last_seen = time.monotonic()

            if message["type"] == "websocket.disconnect":
                break

            frame = message.get("bytes")
            if frame is not None:
                if not session.started:
                    await session.send_error("AUTH_INVALID_TOKEN", "errors.auth.invalid_token")
                    continue
                await session.on_audio(frame)
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
                pumps.append(asyncio.create_task(session.pump_media()))
                continue

            if not session.started:
                await session.send_error("AUTH_INVALID_TOKEN", "errors.auth.invalid_token")
                continue

            if event.type is ControlEventType.SESSION_END:
                break

            logger.info("control event not handled by the call", extra={"type": event.type})
    except WebSocketDisconnect:
        pass
    finally:
        for task in (beat, meter, *pumps):
            task.cancel()
        for task in (beat, meter, *pumps):
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        await session._finish()
