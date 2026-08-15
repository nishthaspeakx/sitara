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
    StreamingSttProvider,
    StreamingTtsProvider,
    SttProvider,
    TtsProvider,
    VoiceProviderName,
    VoiceProviderUnavailable,
)
from sitara_api.voice.providers.routing import Modality, resolve

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
        timeout_seconds=settings.timeout_seconds,
    )


def build_streaming_stt(
    settings: VoiceSettings, *, locale: str
) -> StreamingSttProvider | None:
    """§25.3's live recogniser, or None — and None has two distinct causes.

    **The route is asked first, and it is asked by locale.** CC-010's whole
    ruling is that `hi`/`hi-Latn` have no streaming recogniser and must never be
    handed to an English one, so the lookup that can answer "nobody" runs before
    the lookup that answers "Cartesia". Reversing those two lines is how a
    sensible-looking default gets reintroduced: build the provider first and the
    locale check becomes an `if` someone can delete.

    A missing API key is the OTHER cause, and it is not the same thing — it is
    "provider down" (§30.1: text always works), not "this language has no
    recogniser". The caller distinguishes them by asking `routing.resolve`
    itself; this function returns None for both because in both cases there is
    nothing to call.
    """
    route = resolve(Modality.STREAMING, locale)
    if route.provider is None:
        logger.info("no streaming STT for %s (%s)", locale, route.reason_key)
        return None

    if route.provider is VoiceProviderName.CARTESIA:
        if not settings.cartesia_api_key:
            logger.info("no CARTESIA_API_KEY; live calls are unavailable (§30.1: text works)")
            return None
        from sitara_api.voice.providers.cartesia import CartesiaStreamingSttProvider

        return CartesiaStreamingSttProvider(
            settings.cartesia_api_key, model=settings.stt_model
        )

    # Reached the day `routing.CAPABILITIES` marks a second vendor IMPLEMENTED
    # for streaming without an adapter landing in the same commit. Loud, because
    # the matrix is the thing a release gate reads.
    raise VoiceProviderUnavailable(
        f"routing selected {route.provider!r} for streaming STT and no adapter exists"
    )


def build_streaming_tts(settings: VoiceSettings) -> StreamingTtsProvider | None:
    """Her voice, streamed (§25.3).

    Not locale-routed: §3.3's TTS column covers all three launch locales and
    CC-010's gap is on the STT side only. Keeping the two asymmetric is the same
    discipline `calls_available_in` and `voice_notes_available_in` keep — a
    symmetry invented here would take her voice down in Hindi for a limitation
    that is not hers.
    """
    if settings.tts_provider is not VoiceProviderName.CARTESIA:
        raise VoiceProviderUnavailable(f"no streaming TTS adapter for {settings.tts_provider!r}")
    if not settings.cartesia_api_key:
        return None
    from sitara_api.voice.providers.cartesia import CartesiaStreamingTtsProvider

    return CartesiaStreamingTtsProvider(
        settings.cartesia_api_key,
        model=settings.tts_model,
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
    )
