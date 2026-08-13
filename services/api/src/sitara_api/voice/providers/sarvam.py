"""Sarvam Saaras — §3.3's declared Indic STT comparison arm.

**Status: UNVERIFIED.** No live call has been made against this API and no
fixture has been recorded from it. That word is used exactly as
`panchang/providers` uses it for DivineAPI: the endpoint path and response
shape below are read from documentation, not from a response anyone has seen,
and the skipping test in `tests/voice/` is the honest marker of that. Do not
delete it, and do not promote this provider on the strength of the adapter
existing.

Why it exists anyway
--------------------

§3.2: "the bake-off can swap a PRIMARY only if the challenger wins by ≥0.5 MOS
at equal latency and cost." A bake-off with one implemented arm is not a
bake-off, and CC-009 keeps Sarvam declared precisely so the W3–5 measurement is
a configuration change rather than a milestone.

The claim to be tested is specific. §3.1 credits Saaras with "explicit code-mix
(Hinglish) preservation — strongest Indic STT for our use", and §3.3 makes it
Hinglish's PRIMARY STT. Cartesia Ink documents no code-mix mode at all; what
the live check found is that its `language` parameter selects the SCRIPT of the
Indic span (see `base.stt_language_for`). Whether Saaras does better on real
code-switched speech is the question, and it is not one this file answers.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from sitara_api.voice.providers.base import (
    Transcription,
    TranscriptionRequest,
    VoiceProviderName,
    VoiceProviderUnavailable,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.sarvam.ai"

#: §3.3: "Sarvam Saaras (code-mix mode)" for Hinglish. Env-overridable for the
#: same reason DivineAPI's paths are (`DIVINEAPI_PATH_*`): an unverified path is
#: a guess, and a guess that needs a code change to correct is a guess that
#: stays wrong until someone redeploys.
DEFAULT_PATH = "/speech-to-text"

#: Saaras takes a BCP-47-ish locale rather than a bare language code, and it
#: advertises a code-mix mode — so §2.4's `hi-Latn` may map differently here
#: than it does for Ink. Left explicit rather than shared: the whole point of
#: the comparison arm is that the two vendors may need different requests to
#: honour the same contract ("the transcript comes back in the locale's
#: script"). What that mapping should be is a bake-off finding, not a guess to
#: bake in now.
_LANGUAGE = {"en": "en-IN", "hi": "hi-IN", "hi-Latn": "hi-IN"}


class SarvamSttProvider:
    name = VoiceProviderName.SARVAM

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        path: str = DEFAULT_PATH,
        model: str = "saaras:v3",
        timeout_seconds: float = 20.0,
    ) -> None:
        if not api_key:
            raise VoiceProviderUnavailable("SARVAM_API_KEY is not configured")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._path = path
        self._model = model
        self._timeout = timeout_seconds

    async def transcribe(self, request: TranscriptionRequest) -> Transcription:
        from sitara_api.voice.audio import pcm_to_wav

        language = _LANGUAGE.get(request.locale)
        if language is None:
            raise VoiceProviderUnavailable(
                f"no Saaras language mapping for locale {request.locale!r} (§2.4)"
            )
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}{self._path}",
                    headers={"api-subscription-key": self._api_key},
                    files={
                        "file": (
                            "note.wav",
                            pcm_to_wav(request.audio, request.sample_rate_hz),
                            "audio/wav",
                        )
                    },
                    data={"model": self._model, "language_code": language},
                )
        except httpx.HTTPError as exc:
            logger.warning("sarvam stt call failed: %s", type(exc).__name__)
            raise VoiceProviderUnavailable("sarvam stt unreachable") from exc

        if response.status_code >= 400:
            logger.warning("sarvam stt returned %s", response.status_code)
            raise VoiceProviderUnavailable(f"sarvam stt status {response.status_code}")

        return _transcription_from(response.json(), model=self._model)


def _transcription_from(payload: dict[str, Any], *, model: str) -> Transcription:
    # Documented as `{"transcript": ..., "language_code": ...}`. UNVERIFIED —
    # both spellings are accepted so a first live call fails on something real
    # rather than on a key name.
    text = payload.get("transcript") or payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise VoiceProviderUnavailable("sarvam stt returned no transcript")
    return Transcription(
        text=text.strip(),
        provider=VoiceProviderName.SARVAM,
        model=model,
        detected_language=payload.get("language_code"),
    )
