"""The one voice-provider interface (SPEC §3.2, §3.3).

§3.2 is explicit about why this file exists: the voice ARCHITECTURE is final,
the working PROVIDER MAP is "PROVISIONAL until the W3–5 bake-off", and in the
meantime "engineering builds against adapters". Cartesia is the first
implementation behind this interface (CC-009); Sarvam is the declared Indic STT
comparison arm. Nothing above knows which vendor answered.

Two rules, carried over from `panchang/providers/base.py` because they are the
same two rules and for the same reasons:

1. Adapters return NORMALISED types, never vendor JSON. A bake-off can only
   score two providers against each other if they speak one vocabulary, and a
   vendor's field names must never reach a caller.
2. Adapters raise `VoiceProviderUnavailable`, never an upstream body. §34.4's
   envelope has `VOICE_PROVIDER_UNAVAILABLE` for exactly this.

A third rule belongs to STT alone, and it is the one that will actually bite:

3. **The transcript comes back in the script the LOCALE asks for.** This is a
   contract on the interface, not a detail of any vendor, because it is a §2.4
   requirement: hi-Latn IS Hinglish — Latin script — and hi is Devanagari. It
   is stated here because the obvious implementation gets it wrong; see
   `stt_language_for`.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class VoiceProviderName(StrEnum):
    """§3.3's candidates, as far as M9 implements them.

    ElevenLabs and Azure are §3.3's working primaries and are NOT here: no
    adapter has been written for either, and a member for a provider with no
    implementation would let configuration name one and fail at runtime.
    """

    CARTESIA = "cartesia"
    SARVAM = "sarvam"


class VoiceProviderUnavailable(RuntimeError):
    """The vendor could not answer. Maps to §34.4's VOICE_PROVIDER_UNAVAILABLE.

    Deliberately not carrying the upstream body: §13 keeps vendor payloads out
    of logs and §2.4 keeps vendor English out of a user's screen, and an
    exception that travels tends to end up in both.
    """


class TranscriptionRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    #: 16 kHz mono s16le, per §34.6's binary frame. `repr` is suppressed so a
    #: pytest failure or a traceback never renders a user's voice as hex (§13).
    audio: bytes = Field(repr=False)
    sample_rate_hz: int
    #: A §2.4 LOCALE (`en`, `hi`, `hi-Latn`) — never a vendor language code.
    #: Translating one to the other is the adapter's job precisely because the
    #: translation is not the identity function.
    locale: str


class Transcription(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    provider: VoiceProviderName
    model: str
    #: What the vendor SAYS it heard. Advisory only: §2.4 fixes the reply's
    #: language from the account locale, so this never routes anything. It is
    #: carried for the §3.4 QA corpus and for the bake-off's scoring.
    detected_language: str | None = None
    duration_ms: int | None = None


class SynthesisRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    #: Post-validation text, always. The adapter cannot check that — it is
    #: enforced by `voice.service`, which is the only caller, and asserted from
    #: outside in `tests/voice/test_grounding_parity.py`.
    text: str
    locale: str
    voice_id: str | None = None


class SynthesisResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    audio: bytes = Field(repr=False)
    sample_rate_hz: int
    provider: VoiceProviderName
    model: str
    voice_id: str | None = None


class SttProvider(Protocol):
    """Every STT vendor implements exactly this."""

    name: VoiceProviderName

    async def transcribe(self, request: TranscriptionRequest) -> Transcription: ...


class TtsProvider(Protocol):
    """Every TTS vendor implements exactly this."""

    name: VoiceProviderName

    async def synthesise(self, request: SynthesisRequest) -> SynthesisResult: ...


# ---------------------------------------------------------------------------
# Locale → vendor language, and why it is not a prefix
# ---------------------------------------------------------------------------

#: §2.4's three launch locales mapped to the language code a Whisper-family STT
#: needs to return the RIGHT SCRIPT.
#:
#: The obvious implementation is `locale.split("-")[0]`, which sends `hi-Latn`
#: to `hi`. Verified against the live Cartesia Ink API on 13 Aug 2026, that is
#: wrong in a way no transcript-accuracy metric reports. Reading the same
#: Hinglish audio ("Mera rahu kaal kab hai aaj, and should I start the new job
#: on Monday?"):
#:
#:   language=hi → "मेरा रहुकाल कब है आज? And should I start the new job on Monday?"
#:   language=en → "Mera Rahukaal kab hai aaj? And should I start the new job on Monday?"
#:
#: Both preserve the code-mixing — the English span survives either way, which
#: was the real risk and is not what bites. What the parameter actually selects
#: is the SCRIPT of the Indic span. `hi-Latn` IS Hinglish, and §2.4 makes the
#: whole app native-language with no silent fallback, so a Hinglish thread whose
#: transcripts arrive in Devanagari is the wrong language rendered confidently —
#: the §2.4 violation the locale exists to prevent, arriving through the one
#: door nobody was watching.
#:
#: This is the same shape as M6's `moon_nakshatra_note`: a mapping that is
#: right for two of three cases, wrong for the third, and silent about it.
_STT_LANGUAGE: dict[str, str] = {
    "en": "en",
    # Devanagari. The one locale where the prefix rule happens to be correct.
    "hi": "hi",
    # Latin script, deliberately. See above — this is the whole point of the map.
    "hi-Latn": "en",
}

#: §3.3's TTS column takes the locale's own language: Sonic renders Devanagari
#: from `hi` and romanised Hinglish from `hi` too (§3.3: "Devanagari input to
#: TTS always" for Hindi; Hinglish is 40–60% English tokens read with Hindi
#: intonation, which is what Sonic's native-Hinglish claim is about). The map is
#: separate from the STT one because the two genuinely differ at `hi-Latn`, and
#: one map serving both is how they would quietly be made to agree.
_TTS_LANGUAGE: dict[str, str] = {
    "en": "en",
    "hi": "hi",
    "hi-Latn": "hi",
}


def stt_language_for(locale: str) -> str:
    """The vendor language code that yields the locale's own script."""
    try:
        return _STT_LANGUAGE[locale]
    except KeyError:
        raise VoiceProviderUnavailable(
            f"no STT language mapping for locale {locale!r} — §2.4 admits a locale "
            "only through the §12 gate, and guessing one here would transcribe a "
            "user's voice into a script nobody chose"
        ) from None


def tts_language_for(locale: str) -> str:
    """The vendor language code Tara's reply is spoken in."""
    try:
        return _TTS_LANGUAGE[locale]
    except KeyError:
        raise VoiceProviderUnavailable(
            f"no TTS language mapping for locale {locale!r} (§2.4)"
        ) from None


def supported_locales() -> tuple[str, ...]:
    """The locales voice notes work in. §2.4: never a silent fallback — a
    locale absent here declines rather than being served in another one."""
    return tuple(sorted(set(_STT_LANGUAGE) & set(_TTS_LANGUAGE)))
