"""Provider selection (§3.2's adapter rule, CC-009).

`build_voice_service` returns None when voice is not configured, exactly as
`build_pipeline` returns None on a blank `ANTHROPIC_API_KEY`: an unconfigured
vendor is "provider down", which `/v1/chat/ws/voice-note` serves as §34.4's
`VOICE_PROVIDER_UNAVAILABLE`. It is not a boot failure — text always works
(§30.1), and refusing to start the whole API because voice notes lack a key
would take the chat down with them.
"""

from __future__ import annotations

import logging
from typing import Any

from sitara_api.voice.config import VoiceSettings
from sitara_api.voice.providers.base import (
    SttProvider,
    TtsProvider,
    VoiceProviderName,
    VoiceProviderUnavailable,
)

logger = logging.getLogger(__name__)


def build_stt(settings: VoiceSettings) -> SttProvider | None:
    if settings.stt_provider is VoiceProviderName.CARTESIA:
        if not settings.cartesia_api_key:
            logger.info("no CARTESIA_API_KEY; voice notes are unavailable (§30.1: text works)")
            return None
        from sitara_api.voice.providers.cartesia import CartesiaSttProvider

        return CartesiaSttProvider(
            settings.cartesia_api_key,
            model=settings.stt_model,
            timeout_seconds=settings.timeout_seconds,
        )

    if settings.stt_provider is VoiceProviderName.SARVAM:
        from sitara_api.voice.providers.sarvam import SarvamSttProvider

        if not settings.sarvam_api_key:
            logger.info("no SARVAM_API_KEY; the §3.3 comparison arm is not configured")
            return None
        return SarvamSttProvider(
            settings.sarvam_api_key, timeout_seconds=settings.timeout_seconds
        )

    raise VoiceProviderUnavailable(f"no STT adapter for {settings.stt_provider!r}")


def build_tts(settings: VoiceSettings) -> TtsProvider | None:
    if settings.tts_provider is not VoiceProviderName.CARTESIA:
        # §3.3 lists no non-Cartesia TTS that M9 implements. Naming one in
        # configuration should fail loudly rather than silently fall back to
        # the one that exists — a silent fallback here would put a different
        # voice in Tara's bubble than the one an operator configured.
        raise VoiceProviderUnavailable(f"no TTS adapter for {settings.tts_provider!r}")
    if not settings.cartesia_api_key:
        return None
    from sitara_api.voice.providers.cartesia import CartesiaTtsProvider

    return CartesiaTtsProvider(
        settings.cartesia_api_key,
        model=settings.tts_model,
        voice_id=settings.tara_voice_id,
        timeout_seconds=settings.timeout_seconds,
    )


def build_voice_service(
    *, settings: VoiceSettings, db: Any, crypto: Any, pipeline: Any
) -> Any | None:
    """The §25.4 voice-note service, or None when voice is not configured."""
    if pipeline is None:
        # §9's pipeline is where every validator lives. A voice service without
        # it could transcribe and store but could never answer, and a mic
        # button that records into silence is worse than no mic button.
        return None

    stt = build_stt(settings)
    if stt is None:
        return None

    from sitara_api.voice.service import VoiceNoteService
    from sitara_api.voice.storage import MongoVoiceAssetStore

    tts = build_tts(settings)
    if tts is None:
        # §25.4's voice-note REPLY needs TTS; the user's own notes need only
        # STT. A null synthesiser degrades her side to text bubbles, which is
        # §30.1's rule, rather than taking voice notes down entirely.
        from sitara_api.voice.providers.base import SynthesisRequest, SynthesisResult

        class _NoSynthesis:
            name = VoiceProviderName.CARTESIA

            async def synthesise(self, request: SynthesisRequest) -> SynthesisResult:
                raise VoiceProviderUnavailable("no Tara voice configured (§3.2)")

        tts = _NoSynthesis()

    return VoiceNoteService(
        stt=stt,
        tts=tts,
        pipeline=pipeline,
        asset_store=MongoVoiceAssetStore(db, crypto),
        voice_id=settings.tara_voice_id,
    )
