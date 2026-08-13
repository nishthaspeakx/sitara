"""Cartesia — Sonic for TTS, Ink for STT (CC-009).

**Status: VERIFIED against the live API on 13 Aug 2026** — both endpoints, both
directions, with the shapes below. That word is used the way
`panchang/providers` uses it: Prokerala is VERIFIED, DivineAPI is not, and the
difference is whether anyone has seen the vendor answer. Re-record
`tests/voice/fixtures/` if this file changes.

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
  languages including hi/ta/te/mr/pa/gu/bn. Live calls (§25.3, M10) are a
  different question and this is where it will be asked.
- **Ink documents no code-mix MODE.** It takes one `language` and, in the live
  check, preserved the English span under either value — see
  `base.stt_language_for` for what the parameter actually selects. §3.1 credits
  the explicit code-mix preservation to Sarvam Saaras, not to Cartesia, and
  §3.3 lists Saaras as Hinglish's PRIMARY STT. Cartesia's Hinglish claim is
  about Sonic, the TTS side, where it is well evidenced.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from sitara_api.voice.providers.base import (
    SynthesisRequest,
    SynthesisResult,
    Transcription,
    TranscriptionRequest,
    VoiceProviderName,
    VoiceProviderUnavailable,
    stt_language_for,
    tts_language_for,
)

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
        voice_id = request.voice_id or self._voice_id
        if not voice_id:
            # §3.2's anchor artist is a contracted clone; there is no sensible
            # default voice for Tara and picking a stock one would put a
            # stranger's voice on her name.
            raise VoiceProviderUnavailable("no Tara voice id configured (§3.2)")

        body: dict[str, Any] = {
            "model_id": self._model,
            "transcript": request.text,
            "voice": {"mode": "id", "id": voice_id},
            "language": tts_language_for(request.locale),
            # `raw` + pcm_s16le at 16 kHz is §34.6's binary frame exactly, so
            # her reply and the user's note are the same format on the wire and
            # in storage — one decoder on the client, one codec field in Mongo.
            "output_format": {
                "container": "raw",
                "encoding": "pcm_s16le",
                "sample_rate": self._sample_rate_hz,
            },
        }
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
