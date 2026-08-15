"""The call's two doors (§25.3, §33.5, CC-010, §7.3).

`POST /v1/call/session` is the browser's, cookie-authenticated. It is where
**every reason a call must not happen is evaluated, before a socket exists**:

  1. §33.5's conditional release gate — calls ship only if six measures pass,
     and they do not. So the call is behind a flag, and the flag is off by
     default. §33.5's own sentence for this state: "launch proceeds with text +
     voice notes + Tara audio replies, and calls roll out behind a flag when
     the gate passes."
  2. CC-010's locale ruling — `hi` and `hi-Latn` have no streaming recogniser,
     and an English model fed Hindi audio does not fail, it produces fluent
     nonsense that reaches §9 as the user's question. `routing.calls_available_in`
     is the single implementation of that fact.
  3. §7.3's minute pool — an exhausted pool is not a call that starts and then
     ends; §32.9's warnings exist so it never comes as a surprise, and starting
     at zero would surprise.

Refusing here rather than inside the socket is deliberate. A refusal on an open
socket has to be rendered as a call that failed; a refusal on the grant is
rendered as an affordance that was never offered, which is what §25.3 and
§30.1's "feature-without-permission parity" both want.

`WS /v1/call/media` is `sitara-realtime`'s, service-keyed. `media.py` is its
one description.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import json
import logging
from typing import Any

from fastapi import APIRouter, Header, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sitara_schemas import ErrorCode
from sitara_schemas.voice import HOLDING_PHRASE_AFTER_MS

from sitara_api.auth.router import CurrentSession
from sitara_api.calls.media import (
    SERVICE_KEY_HEADER,
    WS_SESSION_HEADER,
    CallDownFrame,
    CallUpFrame,
)
from sitara_api.chat_orchestration.birth import birth_profile_for, place_label_for
from sitara_api.chat_orchestration.presenter import present_turn
from sitara_api.chat_orchestration.types import Stage, TurnRequest
from sitara_api.chat_orchestration.ws_session import (
    WS_SESSION_TTL_S,
    WsGrant,
    WsTicketService,
    require_service_key,
)
from sitara_api.errors import ApiError
from sitara_api.prototype import calls_enabled as prototype_calls_enabled
from sitara_api.voice.call_metrics import CallObservation
from sitara_api.voice.entitlements import MinuteLedger, MinuteMeter
from sitara_api.voice.providers import browser_bridge
from sitara_api.voice.providers.base import VoiceProviderUnavailable
from sitara_api.voice.providers.registry import build_streaming_stt
from sitara_api.voice.providers.routing import Modality, resolve

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/call", tags=["call"])


class CallSessionPayload(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=64)
    locale: str = Field(min_length=2, max_length=10)


class CallSessionGrant(BaseModel):
    """What the browser needs to open §34.6's call socket, and nothing more.

    `entitlement` is here rather than on the socket because §25.7 item (4) puts
    the plan chip on "a cached entitlement doc (plan, minutes used/quota)". The
    chip's INITIAL value is a read; only its CHANGES are events (§32.9's two
    warnings). A per-second remaining-minutes feed would be §29.2's countdown,
    which this product does not build.
    """

    ticket: str
    ws_url: str
    resume_window_s: int
    entitlement: dict[str, Any]
    captions_default_on: bool
    #: CC-014. Non-null ONLY on a prototype-mode dev machine, and then only for
    #: the locales CC-010 leaves without a recogniser. The client reads it as
    #: "transcribe locally in Chrome and send me finals"; its presence is also
    #: what the screen renders its demo-bridge label from, so the label cannot
    #: drift from the behaviour — one field drives both.
    #:
    #: `None` on every other path, which is every path that ships.
    browser_stt_lang: str | None = None


def _tickets(request: Request) -> WsTicketService:
    return WsTicketService(request.app.state.redis)


@router.post("/session", response_model=CallSessionGrant)
async def call_session(
    payload: CallSessionPayload, request: Request, session: CurrentSession
) -> CallSessionGrant:
    user_id, session_id = session
    settings = request.app.state.settings

    # `prototype.calls_enabled`, not `settings.calls_enabled` — the resolver is
    # `setting OR (prototype AND dev)`, so it can only ever widen and only ever
    # on a laptop. §33.5's gate is untouched and still does not pass.
    if not prototype_calls_enabled(settings):
        # §33.5. Not `SYS_UNAVAILABLE` — nothing is broken and retrying will not
        # help. The client renders the affordance as absent, not as failed.
        raise ApiError(ErrorCode.VOICE_PROVIDER_UNAVAILABLE, "errors.voice.calls_not_enabled")

    route = resolve(Modality.STREAMING, payload.locale)

    # CC-014's demo bridge, asked SEPARATELY and never through `resolve()`.
    #
    # This is the whole shape of the thing: `routing.CAPABILITIES` is untouched,
    # so `calls_available_in("hi")` is still False, §33.5's gate still reads
    # hi/hi-Latn as BLOCKED, and `call.indic_streaming_stt` stays open. A cell
    # added to the matrix would have closed a gate on a capability nobody has.
    #
    # It can only ever WIDEN, and only on a dev machine with prototype mode on
    # — `browser_bridge.recogniser_for` has no parameter that could force it.
    bridge_lang = browser_bridge.recogniser_for(settings, payload.locale)

    if not route.available and bridge_lang is None:
        # CC-010's ruling, read from the one matrix that holds it. The reason
        # key distinguishes "a vendor documents it and nobody has built it"
        # from "nobody offers it", because those are different sentences to a
        # user waiting for Hindi calls.
        #
        # This is still the DEFAULT answer for hi/hi-Latn, and it is what comes
        # back the instant the bridge is unavailable — including when the
        # browser is not Chrome, which the client decides for itself.
        raise ApiError(
            ErrorCode.VOICE_PROVIDER_UNAVAILABLE,
            route.reason_key or "errors.voice.call_language_unavailable",
        )

    ledger = MinuteLedger(request.app.state.db, settings)
    entitlement = await ledger.load(str(user_id), now=dt.datetime.now(dt.UTC))
    if entitlement.exhausted:
        # §32.9 warns at 5 and 2 minutes so this is never the first a user
        # hears of it. Starting a call on an empty pool would be.
        raise ApiError(ErrorCode.VOICE_MINUTES_EXHAUSTED, "errors.voice.minutes_exhausted")

    ticket = await _tickets(request).mint_ticket(
        WsGrant(
            user_id=str(user_id),
            session_id=session_id,
            conversation_id=payload.conversation_id,
            locale=payload.locale,
        )
    )
    return CallSessionGrant(
        ticket=ticket,
        ws_url=settings.realtime_call_ws_url,
        resume_window_s=settings.chat_resume_window_s,
        entitlement=entitlement.as_chip(),
        # §25.3's live captions, on for a first call. `first_call` is derived
        # from the spend, not from a client flag: an account that has never
        # metered a minute has never had a call, and that is a fact the server
        # already holds.
        captions_default_on=entitlement.used_minutes <= 0.0,
        # Null unless CC-014's bridge is both permitted and needed. A locale
        # with a real recogniser never gets it, even in prototype mode: `en`
        # is absent from `BRIDGED_LOCALES` so the demo keeps exercising the
        # vendor path that actually ships.
        browser_stt_lang=bridge_lang if not route.available else None,
    )


class CallRedeemPayload(BaseModel):
    ticket: str = Field(min_length=1, max_length=128)


class CallRedeemResponse(BaseModel):
    ws_session: str
    user_id: str
    conversation_id: str
    locale: str
    expires_in_s: int


@router.post("/ws/redeem", response_model=CallRedeemResponse)
async def call_ws_redeem(
    payload: CallRedeemPayload,
    request: Request,
    service_key: str | None = Header(default=None, alias=SERVICE_KEY_HEADER),
) -> CallRedeemResponse:
    """`sitara-realtime` burns a call ticket and receives the socket's token.

    Deliberately its own endpoint rather than reusing `/v1/chat/ws/redeem`,
    even though both redeem through the same `WsTicketService`. A call and a
    chat are granted under different conditions — §33.5's flag, CC-010's locale
    ruling and §7.3's pool are checked when the CALL ticket is minted and are
    checked for nothing else — and one redemption endpoint serving both would
    make "which gate did this credential pass?" unanswerable from the code. The
    ticket service stays single; only the door is per-transport.
    """
    require_service_key(service_key, request.app.state.settings.service_key)
    ws_session, grant = await _tickets(request).redeem_ticket(payload.ticket)
    return CallRedeemResponse(
        ws_session=ws_session,
        user_id=grant.user_id,
        conversation_id=grant.conversation_id,
        locale=grant.locale,
        expires_in_s=WS_SESSION_TTL_S,
    )


@router.websocket("/media")
async def call_media(websocket: WebSocket) -> None:
    """`sitara-realtime`'s duplex media channel. See `calls/media.py`.

    Everything vendor-shaped and everything database-shaped happens on this
    side of the socket; realtime keeps the §34.6 protocol, the VAD and the
    session clock. The division is §25.7's and the reason is that realtime
    holds no credentials, no model client and no database.
    """
    settings = websocket.app.state.settings
    try:
        require_service_key(
            websocket.headers.get(SERVICE_KEY_HEADER), settings.service_key
        )
    except ApiError:
        # Refused BEFORE the accept. An accepted-then-closed socket looks like a
        # transient failure to a client, and this one is a permanent refusal.
        await websocket.close(code=1008)
        return

    ws_session = websocket.headers.get(WS_SESSION_HEADER)
    if not ws_session:
        await websocket.close(code=1008)
        return
    try:
        grant = await WsTicketService(websocket.app.state.redis).resolve_session(ws_session)
    except ApiError:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    session = _MediaSession(websocket, grant)
    await session.run()


class _MediaSession:
    """One call's worth of vendor connections and turns."""

    def __init__(self, websocket: WebSocket, grant: WsGrant) -> None:
        self._ws = websocket
        self._grant = grant
        self._app = websocket.app
        self._stt: Any = None
        self._speech: asyncio.Task[None] | None = None
        self._turn: asyncio.Task[None] | None = None
        self._stt_seconds = 0.0
        self._tts_seconds = 0.0
        #: §32.9's arithmetic lives HERE, not in realtime. Realtime owns the
        #: clock and reports elapsed seconds; the quota is on this side, so the
        #: pool, the two thresholds and the once-each rule have exactly one
        #: implementation. Splitting them would have put half of §32.9 in a
        #: service that cannot read a subscription.
        self._meter: MinuteMeter | None = None
        #: Which of §25.3's holding phrases plays next. Per CALL, so a caller
        #: who hits three slow turns hears three different lines rather than
        #: the same six words becoming a tic.
        self._holding_index = 0

    # -- lifecycle ---------------------------------------------------------

    async def run(self) -> None:
        ledger = getattr(self._app.state, "minute_ledger", None)
        if ledger is not None:
            entitlement = await ledger.load(
                self._grant.user_id, now=dt.datetime.now(dt.UTC)
            )
            self._meter = MinuteMeter(entitlement=entitlement)
            self._meter.start(0.0)

        voice_settings = getattr(self._app.state, "voice_settings", None)
        provider = None
        if voice_settings is not None:
            provider = build_streaming_stt(voice_settings, locale=self._grant.locale)

        if provider is None:
            # The grant already refused this case; reaching it here means the
            # matrix or the configuration changed under a live ticket. Honest
            # envelope, then close — never an English recogniser (CC-010).
            await self._send(
                CallDownFrame.ERROR,
                {
                    "code": ErrorCode.VOICE_PROVIDER_UNAVAILABLE.value,
                    "message_key": "errors.voice.call_language_unavailable",
                },
            )
            await self._ws.close(code=1011)
            return

        from sitara_api.voice.providers.base import TranscriptionRequest

        try:
            self._stt = await provider.open(
                TranscriptionRequest(audio=b"", sample_rate_hz=16_000, locale=self._grant.locale)
            )
        except VoiceProviderUnavailable:
            await self._send(
                CallDownFrame.ERROR,
                {
                    "code": ErrorCode.VOICE_PROVIDER_UNAVAILABLE.value,
                    "message_key": "errors.voice.provider_unavailable",
                },
            )
            await self._ws.close(code=1011)
            return

        captions = asyncio.create_task(self._pump_captions())
        try:
            await self._pump_frames()
        except WebSocketDisconnect:
            pass
        finally:
            captions.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await captions
            await self._stop_speaking()
            if self._stt is not None:
                with contextlib.suppress(Exception):
                    await self._stt.aclose()

    # -- realtime → here ---------------------------------------------------

    async def _pump_frames(self) -> None:
        while True:
            message = await self._ws.receive()
            if message["type"] == "websocket.disconnect":
                return

            pcm = message.get("bytes")
            if pcm is not None:
                # Straight to the recogniser and then gone. Nothing here holds
                # it (§13, §33.1: call audio is never stored).
                self._stt_seconds += len(pcm) / 2 / 16_000
                try:
                    await self._stt.push(pcm)
                except VoiceProviderUnavailable:
                    await self._send(
                        CallDownFrame.ERROR,
                        {
                            "code": ErrorCode.VOICE_PROVIDER_UNAVAILABLE.value,
                            "message_key": "errors.voice.provider_unavailable",
                        },
                    )
                    return
                continue

            raw = message.get("text")
            if not raw:
                continue
            try:
                frame = json.loads(raw)
            except json.JSONDecodeError:
                continue
            await self._handle(frame)

    async def _handle(self, frame: dict[str, Any]) -> None:
        kind = frame.get("type")

        if kind == CallUpFrame.UTTERANCE.value:
            text = str(frame.get("text") or "").strip()
            client_message_id = str(frame.get("client_message_id") or "")
            if not text:
                return
            if self._turn is not None and not self._turn.done():
                # §7.3: one in-flight utterance max — so this one is not
                # ANSWERED. It is still COMMITTED.
                #
                # This is the milestone's central invariant meeting its most
                # likely counter-example. Speaking over her is not an edge case,
                # it is the feature (§25.3: "barge-in = just speak"), so a
                # second utterance while the first turn is still running is
                # exactly what a working call produces. Dropping the frame here
                # dropped the words with it: call audio is never stored
                # (§13/§33.1), so a sentence that never reached
                # `commit_utterance` is gone for good.
                #
                # Committing without answering leaves the thread honest — the
                # user can see what they said and ask again — which is the same
                # trade `_answer` makes when §9 dies.
                await self._commit_only(text)
                return
            self._turn = asyncio.create_task(self._answer(text, client_message_id))
            return

        if kind == CallUpFrame.CANCEL_SPEECH.value:
            await self._stop_speaking()
            return

        if kind == CallUpFrame.TICK.value:
            await self._tick(float(frame.get("seconds") or 0.0))
            return

        if kind == CallUpFrame.METRIC.value:
            await self._record_metric(frame)
            return

        if kind == CallUpFrame.END.value:
            await self._record_session(float(frame.get("seconds") or 0.0))
            return

    # -- the turn ----------------------------------------------------------

    async def _commit_only(self, text: str) -> None:
        """Put words on the record that nothing is going to answer.

        §7.3 caps the call at one in-flight utterance, and the words that lose
        that race are still words somebody said out loud.
        """
        service = getattr(self._app.state, "call_turns", None)
        if service is None:
            return
        with contextlib.suppress(Exception):
            await service.commit_utterance(
                conversation_id=self._grant.conversation_id,
                text=text,
                locale=self._grant.locale,
                now=dt.datetime.now(dt.UTC),
            )

    async def _answer(self, text: str, client_message_id: str) -> None:
        service = getattr(self._app.state, "call_turns", None)
        if service is None:
            await self._send(
                CallDownFrame.ERROR,
                {
                    "code": ErrorCode.SYS_UNAVAILABLE.value,
                    "message_key": "errors.sys.unavailable",
                },
            )
            return

        stages: asyncio.Queue[str] = asyncio.Queue()

        def on_stage(stage: Stage) -> None:
            stages.put_nowait(stage.value)

        forwarder = asyncio.create_task(self._forward_stages(stages))
        try:
            profile = await birth_profile_for(self._app.state, self._grant.user_id)
            # §25.3's spoken turn reaches the SAME resolution as the typed one.
            # A call that could not say what today's timings are, on an account
            # whose city is stored, is the defect one layer further in.
            place_label = await place_label_for(self._app.state, self._grant.user_id)
            answering = asyncio.create_task(
                service.answer(
                    TurnRequest(
                        user_id=self._grant.user_id,
                        conversation_id=self._grant.conversation_id,
                        text=text,
                        locale=self._grant.locale,
                        now=dt.datetime.now(dt.UTC),
                        profile=profile,
                        place_label=place_label,
                    ),
                    on_stage=on_stage,
                )
            )
            # §25.3: "thinking … max 1.8s before she speaks a holding phrase".
            #
            # A CEILING ON SILENCE, not a delay to wait out — if §9 answers in
            # 400ms she answers in 400ms and nothing below runs. §9's three
            # model round-trips are in series, so a real reply is often ~5.8s,
            # and the phrase is what turns four seconds of nothing into a pause
            # somebody designed.
            await asyncio.wait({answering}, timeout=HOLDING_PHRASE_AFTER_MS / 1000)
            if not answering.done():
                # AWAITED, not fired-and-forgotten. Both streams write PCM to
                # the same socket, so overlapping them interleaves two voices
                # into noise. Holding the answer's audio behind the phrase costs
                # the phrase's length — under a second — and is the difference
                # between a designed pause and a broken one.
                #
                # It goes through `self._speech` so §25.3's barge-in reaches it:
                # `_stop_speaking` cancels that slot, and while the phrase was
                # awaited inline the slot was empty — she would have talked over
                # someone interrupting her. Filler is the thing it should be
                # EASIEST to interrupt.
                self._speech = asyncio.create_task(
                    self._speak_holding_phrase(client_message_id)
                )
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await self._speech
                self._speech = None
            # A barge-in over the phrase does not abandon the answer. §7.3
            # already decides what happens to words spoken into an in-flight
            # turn — they are committed unanswered — and cancelling here would
            # throw away a turn §9 has nearly finished paying for.
            spoken = await answering
        finally:
            forwarder.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await forwarder

        if spoken.turn is None:
            # The transcript is already in the thread — that is the point of
            # `commit_utterance`. Realtime turns this into §25.3's degrade.
            code, key = spoken.failure or ("SYS_INTERNAL", "errors.sys.internal")
            await self._send(
                CallDownFrame.ERROR,
                {"code": code, "message_key": key, "client_message_id": client_message_id},
            )
            return

        turn = present_turn(spoken.turn)
        # Her words FIRST, always, and then the audio rendered from them. The
        # ordering is §25.4's transcript-toggle rule and it holds here for a
        # stronger reason: if synthesis dies, the reply is already on screen.
        await self._send(
            CallDownFrame.TURN,
            {"client_message_id": client_message_id, "turn": turn.model_dump(mode="json")},
        )
        self._speech = asyncio.create_task(self._speak(spoken.turn, client_message_id))

    async def _speak_holding_phrase(self, client_message_id: str) -> None:
        """§25.3's holding phrase — her voice, and not her answer.

        Everything about this method is arranged so that a phrase can never
        become an answer, and a failure to say one can never become a failure to
        answer:

        · **Nothing is stored.** No `commit_utterance`, no message, no turn. The
          phrase makes no claim, so there is nothing for cite-or-die to check —
          and putting it in the thread would carry filler into the Journal, the
          §32.11 handoff transcript and tomorrow's memory retrieval.
        · **`holding: True` rides on `tts_start`.** Realtime needs it to keep
          §33.5's `first_audio_seconds` timing the ANSWER, and the client needs
          it to return to `thinking` rather than showing a mic-live indicator
          over a turn still in flight.
        · **Any failure is swallowed into silence.** A dead synthesiser must
          cost the courtesy and nothing else: the answer is still coming, and
          raising here would abandon a turn that §9 is in the middle of. §25.3's
          degrade ladder is for the ANSWER failing, not the filler.
        · **The `client_message_id` is the utterance's**, so a barge-in that
          arrives mid-phrase is attributed to the same utterance the user is
          interrupting.
        """
        service = getattr(self._app.state, "call_turns", None)
        if service is None:
            return
        message_id = client_message_id
        chunk_seq = 0
        try:
            await self._send(
                CallDownFrame.TTS_START,
                {
                    "client_message_id": message_id,
                    "sample_rate_hz": 16_000,
                    "holding": True,
                },
            )
            async for chunk in service.speak_holding_phrase(
                locale=self._grant.locale, turn_index=self._holding_index
            ):
                await self._ws.send_bytes(chunk)
                chunk_seq += 1
                # It is real synthesis and it costs what it costs — §33.5's
                # cost measure would understate every call that used one if
                # this were excluded. Metering the truth is the whole reason
                # `call_metrics` and `call_gate` are separate files.
                self._tts_seconds += len(chunk) / 2 / 16_000
        except asyncio.CancelledError:
            # §25.3's barge-in landed on the phrase. The user talked over
            # filler, which is exactly what filler is for.
            await self._send(
                CallDownFrame.TTS_CANCELLED,
                {
                    "client_message_id": message_id,
                    "after_chunk_seq": chunk_seq - 1 if chunk_seq else None,
                    "reason": "user_speech",
                },
            )
            raise
        except Exception:
            # Including `MissingString`: §2.4 forbids falling back to English,
            # so a locale whose phrase went missing gets the silence it would
            # have had. Logged, never spoken in the wrong language.
            logger.warning("holding phrase not spoken", exc_info=True)
            with contextlib.suppress(Exception):
                await self._send(
                    CallDownFrame.TTS_CANCELLED,
                    {
                        "client_message_id": message_id,
                        "after_chunk_seq": chunk_seq - 1 if chunk_seq else None,
                        "reason": "synthesis_failed",
                    },
                )
            return
        else:
            await self._send(
                CallDownFrame.TTS_END,
                {"client_message_id": message_id, "chunks": chunk_seq},
            )
        finally:
            # Rotate whether or not it played, so two consecutive slow turns
            # never draw the same line twice — the tic this set exists to avoid.
            self._holding_index += 1

    async def _forward_stages(self, stages: asyncio.Queue[str]) -> None:
        while True:
            stage = await stages.get()
            await self._send(CallDownFrame.STAGE, {"stage": stage})

    # -- synthesis ---------------------------------------------------------

    async def _speak(self, turn: Any, client_message_id: str) -> None:
        service = self._app.state.call_turns
        chunk_seq = 0
        await self._send(
            CallDownFrame.TTS_START,
            {"client_message_id": client_message_id, "sample_rate_hz": 16_000},
        )
        try:
            async for chunk in service.speak(turn, locale=self._grant.locale):
                await self._ws.send_bytes(chunk)
                chunk_seq += 1
                self._tts_seconds += len(chunk) / 2 / 16_000
        except asyncio.CancelledError:
            # §25.3's barge-in. Realtime asked; realtime knows why.
            await self._send(
                CallDownFrame.TTS_CANCELLED,
                {
                    "client_message_id": client_message_id,
                    "after_chunk_seq": chunk_seq - 1 if chunk_seq else None,
                    "reason": "user_speech",
                },
            )
            raise
        except VoiceProviderUnavailable:
            # §8's ladder: voice fails, text continues. Her words are already on
            # screen — they crossed on `turn` before a single byte of audio.
            logger.warning("call synthesis failed mid-utterance; the reply stays text (§8)")
            await self._send(
                CallDownFrame.TTS_CANCELLED,
                {
                    "client_message_id": client_message_id,
                    "after_chunk_seq": chunk_seq - 1 if chunk_seq else None,
                    "reason": "provider_failed",
                },
            )
            return
        await self._send(
            CallDownFrame.TTS_END,
            {"client_message_id": client_message_id, "chunks": chunk_seq},
        )

    async def _stop_speaking(self) -> None:
        if self._speech is None or self._speech.done():
            return
        self._speech.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await self._speech

    # -- captions ----------------------------------------------------------

    async def _pump_captions(self) -> None:
        try:
            async for event in self._stt:
                await self._send(
                    CallDownFrame.CAPTION, {"text": event.text, "is_final": event.is_final}
                )
        except VoiceProviderUnavailable:
            await self._send(
                CallDownFrame.ERROR,
                {
                    "code": ErrorCode.VOICE_PROVIDER_UNAVAILABLE.value,
                    "message_key": "errors.voice.provider_unavailable",
                },
            )

    # -- metering and metrics ----------------------------------------------

    async def _tick(self, seconds: float) -> None:
        """§32.9, evaluated against the pool this side owns.

        `seconds` is realtime's METERED elapsed time, not wall clock: §32.9
        stops metering the moment a session is text-mode and §32.11 restarts it
        only on resume, and only realtime knows which of those the call is in.
        Two clocks would disagree by exactly the time a user spent reading a
        handoff notice, which is the time they must not be charged for.
        """
        if self._meter is None:
            return
        # The meter measures from a monotonic zero; realtime's total IS that
        # measurement, so it is fed in as the elapsed value rather than
        # re-derived here from a clock this side never started.
        self._meter.elapsed_seconds = seconds
        for threshold in self._meter.tick(0.0):
            await self._send(
                CallDownFrame.ENTITLEMENT_WARNING,
                {
                    "minutes_left": threshold,
                    "minutes_quota": self._meter.entitlement.quota_minutes,
                    "plan": self._meter.entitlement.plan.value,
                    # §2.4: a KEY, never a sentence. A sentence on the wire is a
                    # sentence no §14 reviewer saw.
                    "message_key": "ui.call.warning_minutes",
                },
            )
        if self._meter.exhausted(0.0):
            # Never a hard drop (§32.9). Realtime turns this into the same
            # text handoff a network degrade produces, and the transcript is
            # already in the thread either way.
            await self._send(CallDownFrame.EXHAUSTED, {"plan": self._meter.entitlement.plan.value})

    async def _record_metric(self, frame: dict[str, Any]) -> None:
        metrics = getattr(self._app.state, "call_metrics", None)
        if metrics is None:
            return
        try:
            observation = CallObservation(str(frame.get("observation")))
        except ValueError:
            # A metric name nothing reads is worse than none: it looks like
            # evidence in a log and reaches no gate.
            logger.warning("unknown call observation reported; dropping it")
            return
        await metrics.record(
            observation,
            value=float(frame.get("value") or 1.0),
            locale=frame.get("locale"),
        )

    async def _record_session(self, seconds: float) -> None:
        """One call's spend, at its end (§25.7).

        **Not `_meter`.** It was — and `self._meter` is also the `MinuteMeter`
        attribute, so the attribute shadowed the method and an `end` frame
        raised `TypeError: 'MinuteMeter' object is not callable`. The call was
        then never written to `voice_sessions`: minutes never accrued, the pool
        never depleted, and §7.3's entitlement system quietly did nothing at
        all. No test caught it — none drives an `end` frame through the real
        router — and `pyright` did, as a redeclaration.
        """
        ledger = getattr(self._app.state, "minute_ledger", None)
        if ledger is None:
            return
        metrics = getattr(self._app.state, "call_metrics", None)
        if metrics is not None:
            # §33.5's cost INPUTS, never a cost. `call_metrics` records why.
            await metrics.record(
                CallObservation.STT_STREAM_SECONDS, value=round(self._stt_seconds, 3)
            )
            await metrics.record(
                CallObservation.TTS_STREAM_SECONDS, value=round(self._tts_seconds, 3)
            )
        with contextlib.suppress(Exception):
            await ledger.record(
                user_id=self._grant.user_id,
                conversation_id=self._grant.conversation_id,
                seconds=seconds,
                provider_mix={
                    "stt_seconds": round(self._stt_seconds, 3),
                    "tts_seconds": round(self._tts_seconds, 3),
                },
                latency_stats={},
                now=dt.datetime.now(dt.UTC),
            )

    # -- sending -----------------------------------------------------------

    async def _send(self, kind: CallDownFrame, payload: dict[str, Any]) -> None:
        with contextlib.suppress(Exception):
            await self._ws.send_text(json.dumps({"type": kind.value, **payload}))
