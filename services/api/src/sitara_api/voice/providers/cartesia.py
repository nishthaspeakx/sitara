"""Cartesia — Sonic for TTS, Ink for STT (CC-009).

**Status, per modality, because they differ:**

- **BATCH (`POST /stt`, `POST /tts/bytes`) — VERIFIED** against the live API on
  13 Aug 2026, both directions, with the shapes below and recorded fixtures in
  `tests/voice/fixtures/`.
- **STREAMING (`wss://…/stt/websocket`, `wss://…/tts/websocket`) — VERIFIED
  against the live API on 15 Aug 2026**, both sockets, with the fixture in
  `tests/voice/fixtures/streaming_en.json`. It was written from documentation
  and shipped UNVERIFIED; the first live call is what corrected it.

**What the live run corrected, and what only a vendor could have told us:**

- **`context_id` is REQUIRED on the TTS websocket.** Without it Sonic answers
  every single utterance with `{"type":"error","title":"context_id is
  invalid"}` — so a call reached her validated words and then fell silent,
  every time. 1,457 tests were green: none of them reaches a vendor, and the
  vendor was the only thing that knew. `tts_stream_body` now carries it.
- **Ink emits a final transcript PER PHRASE, not per utterance.** The recorded
  fixture shows one spoken sentence returning two `is_final` frames ("Saturn is
  moving through your tenth house today." then "Go slowly."). `CallSttStream`
  currently treats each as a complete turn, so a speaker who pauses mid-thought
  has their sentence cut in two and answered twice. **Known, not yet handled** —
  it needs a debounce whose length is a product decision, not a reflex.
- **First audio was 6.8s end to end on a cold call**, against §33.5's 1.2s
  ceiling. §7.3 asks for "connection pooling per provider" and none is built;
  that is the first thing to try.

The batch/streaming split was never pedantry: §33.5's gate turns on p95
first-response audio and barge-in success, both properties of the streaming
path alone, and the batch verification said nothing about either.

What CC-009 does and does not claim
-----------------------------------

§3.2 makes the §3.3 provider MAP provisional and the ACCEPTANCE GATE final —
eight measures (latency, concurrency, pronunciation error rate, code-switch
accuracy, cost, failover, an emotional-consistency panel, and contractual
rights) that a provider must pass to SHIP. **No bake-off has run.** This adapter
is the first implementation behind §3.2's "engineering builds against adapters",
and nothing here asserts the gate is met.

Two limits found while verifying, which the bake-off will need to weigh:

- **Ink's streaming endpoint is English-only today** (`wss://…/stt/websocket`
  documents `language`: "currently only `en` supported"). Voice notes are
  unaffected — a note is a complete recording and §28.3 wants the transcript
  "<2s post-release", so the BATCH endpoint is the right fit and it carries 49
  languages including hi/ta/te/mr/pa/gu/bn. Live calls (§25.3, M9-P10b) are a
  different question and this is where it will be asked.
- **Ink documents no code-mix MODE.** It takes one `language` and, in the live
  check, preserved the English span under either value — see
  `base.stt_language_for` for what the parameter actually selects. §3.1 credits
  the explicit code-mix preservation to Sarvam Saaras, not to Cartesia, and
  §3.3 lists Saaras as Hinglish's PRIMARY STT. Cartesia's Hinglish claim is
  about Sonic, the TTS side, where it is well evidenced.
"""

from __future__ import annotations

import base64
import contextlib
import json
import logging
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import httpx
import websockets

from sitara_api.voice.providers.base import (
    SynthesisRequest,
    SynthesisResult,
    TranscriptEvent,
    Transcription,
    TranscriptionRequest,
    VoiceProviderName,
    VoiceProviderUnavailable,
    stt_language_for,
    tts_language_for,
)
from sitara_api.voice.providers.voices import voice_for

logger = logging.getLogger(__name__)

#: Cartesia pins its API by date header. Bumping this is a vendor migration:
#: re-record the fixtures and re-run the live check before changing it.
CARTESIA_VERSION = "2026-03-01"
DEFAULT_BASE_URL = "https://api.cartesia.ai"

#: §3.3 fixes the tier, never the point release — same discipline as
#: `ChatSettings.conversation_model` pinning the Claude tier.
DEFAULT_STT_MODEL = "ink-whisper"
DEFAULT_TTS_MODEL = "sonic-3.5"


class CartesiaSttProvider:
    """Ink, over the batch endpoint (`POST /stt`)."""

    name = VoiceProviderName.CARTESIA

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_STT_MODEL,
        timeout_seconds: float = 20.0,
    ) -> None:
        if not api_key:
            raise VoiceProviderUnavailable("CARTESIA_API_KEY is not configured")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout_seconds

    async def transcribe(self, request: TranscriptionRequest) -> Transcription:
        language = stt_language_for(request.locale)
        # Raw PCM is uploaded as a WAV: the endpoint accepts `encoding` +
        # `sample_rate` query params for headerless PCM, but a container the
        # vendor can parse unambiguously is one fewer thing to be wrong about
        # a format we already own end to end.
        from sitara_api.voice.audio import pcm_to_wav

        files = {
            "file": ("note.wav", pcm_to_wav(request.audio, request.sample_rate_hz), "audio/wav"),
        }
        data = {"model": self._model, "language": language}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/stt",
                    headers=self._headers(),
                    files=files,
                    data=data,
                )
        except httpx.HTTPError as exc:
            # The audio is never logged, and neither is the transcript (§13).
            logger.warning("cartesia stt call failed: %s", type(exc).__name__)
            raise VoiceProviderUnavailable("cartesia stt unreachable") from exc

        if response.status_code >= 400:
            logger.warning("cartesia stt returned %s", response.status_code)
            raise VoiceProviderUnavailable(f"cartesia stt status {response.status_code}")

        return _transcription_from(response.json(), model=self._model)

    def _headers(self) -> dict[str, str]:
        return {
            "Cartesia-Version": CARTESIA_VERSION,
            "Authorization": f"Bearer {self._api_key}",
        }


class CartesiaTtsProvider:
    """Sonic, over `POST /tts/bytes`."""

    name = VoiceProviderName.CARTESIA

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_TTS_MODEL,
        voice_id: str | None = None,
        sample_rate_hz: int = 16_000,
        timeout_seconds: float = 20.0,
    ) -> None:
        if not api_key:
            raise VoiceProviderUnavailable("CARTESIA_API_KEY is not configured")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._voice_id = voice_id
        self._sample_rate_hz = sample_rate_hz
        self._timeout = timeout_seconds

    async def synthesise(self, request: SynthesisRequest) -> SynthesisResult:
        # Resolved from the LOCALE (`providers/voices.py`), never from a value
        # threaded down from settings. `request.voice_id` stays as a per-request
        # override for a bake-off harness; every production caller leaves it
        # None. An unmapped locale raises rather than borrowing a voice.
        voice_id = request.voice_id or voice_for(request.locale)

        body = tts_body(
            text=request.text,
            voice_id=voice_id,
            locale=request.locale,
            model=self._model,
            sample_rate_hz=self._sample_rate_hz,
        )
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/tts/bytes",
                    headers={**self._headers(), "Content-Type": "application/json"},
                    json=body,
                )
        except httpx.HTTPError as exc:
            logger.warning("cartesia tts call failed: %s", type(exc).__name__)
            raise VoiceProviderUnavailable("cartesia tts unreachable") from exc

        if response.status_code >= 400:
            logger.warning("cartesia tts returned %s", response.status_code)
            raise VoiceProviderUnavailable(f"cartesia tts status {response.status_code}")

        return SynthesisResult(
            audio=response.content,
            sample_rate_hz=self._sample_rate_hz,
            provider=self.name,
            model=self._model,
            voice_id=voice_id,
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Cartesia-Version": CARTESIA_VERSION,
            "Authorization": f"Bearer {self._api_key}",
        }


# ---------------------------------------------------------------------------
# Streaming (M9-P10b, §25.3) — UNVERIFIED. See the module docstring.
# ---------------------------------------------------------------------------

#: The vendor authenticates a websocket by query parameter in its own examples.
#: We send a header instead. §13 keeps secrets out of logs, and a URL is the one
#: string that reliably reaches an access log, a proxy trace, an exception
#: message and a metrics label — four places a key has no business being. If a
#: future vendor version refuses the header, that is a finding to record here,
#: not a reason to put the key back in the URL.


def _ws_url(base_url: str, path: str, params: dict[str, str]) -> str:
    scheme = "wss" if base_url.startswith("https") else "ws"
    host = base_url.split("://", 1)[-1].rstrip("/")
    query = "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
    return f"{scheme}://{host}{path}?{query}"


class CartesiaSttStream:
    """One live Ink connection, for the length of one call.

    Two tasks, not one loop: the caller pushes PCM from wherever its audio comes
    from, and results arrive whenever the recogniser has them. A design that
    read a transcript after each push would have made every 20 ms of microphone
    wait for a network round trip, which is the latency §33.5 measures.

    **There is no method here that returns audio, and that is deliberate**
    (§13, §33.1: call audio is never stored). The bytes go in and transcripts
    come out; nothing in this object holds a buffer of what was said aloud.
    """

    def __init__(self, connection: Any, *, model: str) -> None:
        self._ws = connection
        self._model = model
        self._closed = False

    async def push(self, pcm: bytes) -> None:
        if self._closed:
            raise VoiceProviderUnavailable("cartesia stt stream is closed")
        try:
            await self._ws.send(pcm)
        except Exception as exc:  # noqa: BLE001 - vendor lib raises its own tree
            self._closed = True
            logger.warning("cartesia stt stream push failed: %s", type(exc).__name__)
            raise VoiceProviderUnavailable("cartesia stt stream lost") from exc

    def __aiter__(self) -> AsyncIterator[TranscriptEvent]:
        return self._events()

    async def _events(self) -> AsyncIterator[TranscriptEvent]:
        try:
            async for message in self._ws:
                if isinstance(message, bytes):
                    # Ink sends JSON. A binary frame here is a protocol change,
                    # and guessing at it would be inventing a transcript.
                    continue
                try:
                    frame = json.loads(message)
                except json.JSONDecodeError:
                    continue
                kind = frame.get("type")
                if kind == "error":
                    # The vendor's message is NOT forwarded (§13, §2.4): it is
                    # English prose from a third party and it would reach a
                    # screen. The type name is enough to debug from.
                    logger.warning("cartesia stt stream reported an error frame")
                    raise VoiceProviderUnavailable("cartesia stt stream errored")
                if kind == "done":
                    return
                if kind != "transcript":
                    continue
                text = frame.get("text")
                if not isinstance(text, str) or not text.strip():
                    # An empty final is silence, not a turn. Passing it on would
                    # send §9 an empty question and get a real answer to it.
                    continue
                yield TranscriptEvent(text=text.strip(), is_final=bool(frame.get("is_final")))
        except VoiceProviderUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("cartesia stt stream ended: %s", type(exc).__name__)
            raise VoiceProviderUnavailable("cartesia stt stream lost") from exc
        finally:
            self._closed = True

    async def aclose(self) -> None:
        self._closed = True
        with contextlib.suppress(Exception):
            await self._ws.close()


class CartesiaStreamingSttProvider:
    """Ink, over `wss://…/stt/websocket` (§25.3's live call).

    English only, and that is the vendor's limit rather than ours — which is
    why `routing.resolve(Modality.STREAMING, "hi")` returns no provider and this
    class is never constructed for a Hindi call. It does not re-check the
    locale: two places deciding the same thing is how one of them ends up
    deciding it differently, and `routing` is the one that CC-010 names.
    """

    name = VoiceProviderName.CARTESIA
    modality = "streaming"

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_STT_MODEL,
        sample_rate_hz: int = 16_000,
    ) -> None:
        if not api_key:
            raise VoiceProviderUnavailable("CARTESIA_API_KEY is not configured")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._sample_rate_hz = sample_rate_hz

    async def open(self, request: TranscriptionRequest) -> CartesiaSttStream:
        if request.audio:
            # The bytes belong on `push`. Accepting them here would give the
            # interface two ways to send audio and one of them would rot.
            raise VoiceProviderUnavailable("a streaming request carries no audio up front")
        language = stt_language_for(request.locale)
        url = _ws_url(
            self._base_url,
            "/stt/websocket",
            {
                "model": self._model,
                "language": language,
                "encoding": "pcm_s16le",
                "sample_rate": str(request.sample_rate_hz or self._sample_rate_hz),
            },
        )
        try:
            connection = await websockets.connect(url, additional_headers=self._headers())
        except Exception as exc:  # noqa: BLE001
            logger.warning("cartesia stt websocket refused: %s", type(exc).__name__)
            raise VoiceProviderUnavailable("cartesia stt stream unreachable") from exc
        return CartesiaSttStream(connection, model=self._model)

    def _headers(self) -> dict[str, str]:
        return {
            "Cartesia-Version": CARTESIA_VERSION,
            "Authorization": f"Bearer {self._api_key}",
        }


class CartesiaStreamingTtsProvider:
    """Sonic, over `wss://…/tts/websocket`.

    §25.3 wants TTFB, not a file: the whole reason a call streams is that her
    first syllable must land inside §33.5's 1.2s while the rest is still being
    rendered. The iterator is also the cancellation handle — closing it on a
    barge-in stops the vendor mid-utterance instead of paying for audio the user
    has already talked over.
    """

    name = VoiceProviderName.CARTESIA
    modality = "streaming"

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_TTS_MODEL,
        voice_id: str | None = None,
        sample_rate_hz: int = 16_000,
    ) -> None:
        if not api_key:
            raise VoiceProviderUnavailable("CARTESIA_API_KEY is not configured")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._voice_id = voice_id
        self._sample_rate_hz = sample_rate_hz

    async def stream(self, request: SynthesisRequest) -> AsyncIterator[bytes]:
        # Same rule as the batch adapter: resolved from the LOCALE, and an
        # unmapped locale declines rather than borrowing a voice (CC-008).
        voice_id = request.voice_id or voice_for(request.locale)

        url = _ws_url(self._base_url, "/tts/websocket", {"cartesia_version": CARTESIA_VERSION})
        body = tts_stream_body(
            text=request.text,
            voice_id=voice_id,
            locale=request.locale,
            model=self._model,
            sample_rate_hz=self._sample_rate_hz,
        )

        try:
            connection = await websockets.connect(url, additional_headers=self._headers())
        except Exception as exc:  # noqa: BLE001
            logger.warning("cartesia tts websocket refused: %s", type(exc).__name__)
            raise VoiceProviderUnavailable("cartesia tts stream unreachable") from exc

        try:
            await connection.send(json.dumps(body))
            async for message in connection:
                if isinstance(message, bytes):
                    yield message
                    continue
                try:
                    frame = json.loads(message)
                except json.JSONDecodeError:
                    continue
                kind = frame.get("type")
                if kind == "chunk":
                    data = frame.get("data")
                    if isinstance(data, str) and data:
                        yield base64.b64decode(data)
                    continue
                if kind == "done":
                    return
                if kind == "error":
                    logger.warning("cartesia tts stream reported an error frame")
                    raise VoiceProviderUnavailable("cartesia tts stream errored")
        except VoiceProviderUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("cartesia tts stream ended: %s", type(exc).__name__)
            raise VoiceProviderUnavailable("cartesia tts stream lost") from exc
        finally:
            # Reached on a barge-in too: closing the generator runs this, which
            # is what actually stops the vendor rendering.
            with contextlib.suppress(Exception):
                await connection.close()

    def _headers(self) -> dict[str, str]:
        return {
            "Cartesia-Version": CARTESIA_VERSION,
            "Authorization": f"Bearer {self._api_key}",
        }


# ---------------------------------------------------------------------------
# §4's persona — and why NO prosody controls are sent
# ---------------------------------------------------------------------------
#
# `speed` and `emotion` are NOT in the body below, and their absence is a
# measurement rather than an oversight.
#
# **Measured against the live sonic-3.5 endpoint, 16 Aug 2026.** Every control
# returns HTTP 200 and none of them does anything:
#
#   baseline        mean 4.46s   spread 0.32s      (n=4, one Hindi sentence)
#   speed=slow      mean 4.38s   spread 0.56s
#   speed=slowest   mean 4.16s   spread 0.64s
#   speed=fastest   mean 4.38s   spread 0.24s
#
# `slowest` and `fastest` sit inside each other's noise, and `slowest` came back
# SHORTER than baseline. Sonic is generative, so the same text twice differs by
# up to 0.6s on its own; the parameter is not moving anything.
#
# A 200 is not evidence, which is the trap worth naming: the endpoint 404s on a
# bad `model_id`, 404s on a bad voice id and 400s on `language: "zz"` — but it
# returns 200 for `{"this_field_is_invented": true}` and for `speed: "banana"`.
# It validates the fields it knows and SILENTLY DROPS the ones it does not. So
# `__experimental_controls` (Sonic-1 era) also "succeeds" on 3.5, and any
# plausible-looking control added here would sit in the source looking
# effective forever.
#
# This is the `context_id` lesson inverted. There, a missing field produced a
# loud vendor error and a silent product failure. Here, an unsupported field
# produces a cheerful 200 and a comment that lies. Both are only visible from a
# real call.
#
# **So §4's register comes from the two levers that demonstrably work:**
#
#   1. the VOICE itself (`providers/voices.py`) — chosen per locale, and the
#      only place warmth is actually decided;
#   2. the TEXT, via §3.4's dictionary, which inserts real pauses. Its
#      respellings carry double spaces ("राहु  काल"), and that whitespace is a
#      prosodic instruction the model does honour — it is why the dictionary
#      improves pacing on tradition terms and not only pronunciation.
#
# If a future Sonic version documents real controls, add them HERE, and prove
# they moved the duration before believing the 200.


def tts_body(
    *,
    text: str,
    voice_id: str,
    locale: str,
    model: str = DEFAULT_TTS_MODEL,
    sample_rate_hz: int = 16_000,
) -> dict[str, Any]:
    """The Sonic REST request, in ONE place.

    Shares `_persona_controls` with the streaming body below, so her voice
    cannot drift between a voice-note reply and a live call — which is the
    same divergence `tts_stream_body`'s own header records about the recorder,
    pointed at prosody instead of at shape.
    """
    return {
        "model_id": model,
        "transcript": text,
        "voice": {"mode": "id", "id": voice_id},
        "language": tts_language_for(locale),
        # `raw` + pcm_s16le at 16 kHz is §34.6's binary frame exactly, so her
        # reply and the user's note are the same format on the wire and in
        # storage — one decoder on the client, one codec field in Mongo.
        "output_format": {
            "container": "raw",
            "encoding": "pcm_s16le",
            "sample_rate": sample_rate_hz,
        },
    }


def tts_stream_body(
    *,
    text: str,
    voice_id: str,
    locale: str,
    model: str = DEFAULT_TTS_MODEL,
    sample_rate_hz: int = 16_000,
) -> dict[str, Any]:
    """The Sonic websocket request, in ONE place.

    `record_streaming.py` used to rebuild this, with a comment claiming it was
    "the adapter's own body". It was not, and the divergence cost a live
    verification cycle: the adapter was fixed, the recorder still sent the old
    shape, and the vendor returned the identical error — which read as "the fix
    did not work" rather than "the recorder is testing something else".

    So the recorder now calls this. A fixture recorded from a request the
    adapter does not send is a fixture that proves nothing about the adapter.
    """
    return {
        **tts_body(
            text=text,
            voice_id=voice_id,
            locale=locale,
            model=model,
            sample_rate_hz=sample_rate_hz,
        ),
        # **REQUIRED — found live, 15 Aug 2026.** Without it Sonic answers every
        # utterance with `{"type":"error","title":"context_id is invalid"}`, so a
        # call reached her validated words and then fell silent, every time. The
        # whole suite was green: no test reaches a vendor, and the vendor was the
        # only thing that knew.
        #
        # `uuid4().hex` because the vendor constrains the charset to
        # alphanumerics, underscores and hyphens — a §34.6 `client_message_id`
        # would eventually carry something outside it.
        "context_id": uuid4().hex,
        "continue": False,
    }


def _transcription_from(payload: dict[str, Any], *, model: str) -> Transcription:
    """Normalise Ink's response.

    Shape as verified live:
    `{"type","duration","language","is_final","request_id","text"}`.
    A missing `text` is a failure, not an empty transcript: handing §9 an empty
    string would run the whole pipeline on nothing and answer a question the
    user never asked.
    """
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise VoiceProviderUnavailable("cartesia stt returned no transcript")
    duration = payload.get("duration")
    return Transcription(
        text=text.strip(),
        provider=VoiceProviderName.CARTESIA,
        model=model,
        detected_language=payload.get("language"),
        duration_ms=int(duration * 1000) if isinstance(duration, (int, float)) else None,
    )
