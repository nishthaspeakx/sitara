"""Voice configuration (§3.2, §3.3, CC-009).

Which provider runs is CONFIGURATION, not code — §3.2's "engineering builds
against adapters" is only true if swapping one is an env var. Cartesia is M9's
default because CC-009 chose it; Sarvam is selectable today as §3.3's declared
Indic STT comparison arm, which is what makes the W3–5 bake-off a measurement
rather than a rewrite.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from sitara_api.voice.providers.base import VoiceProviderName


class VoiceSettings(BaseSettings):
    """Env-overridable, prefix `VOICE_` except where the vendor names the key."""

    # populate_by_name: a `validation_alias` REPLACES the field name, so
    # `VoiceSettings(cartesia_api_key=...)` would silently produce None while
    # looking like it worked. It did exactly that in `ChatSettings` for a whole
    # milestone, and again in `MemorySettings` — both spellings must bind.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="VOICE_",
        populate_by_name=True,
    )

    #: CC-009's default. §3.3's map stays PROVISIONAL and §3.2's acceptance gate
    #: is unchanged and unmet — this names the first implementation, not a
    #: bake-off result.
    stt_provider: VoiceProviderName = VoiceProviderName.CARTESIA
    tts_provider: VoiceProviderName = VoiceProviderName.CARTESIA

    cartesia_api_key: str | None = Field(default=None, validation_alias="CARTESIA_API_KEY")
    #: §3.3's declared Indic STT comparison arm. Absent today; the adapter says
    #: so rather than pretending, on the DivineAPI-unverified precedent.
    sarvam_api_key: str | None = Field(default=None, validation_alias="SARVAM_API_KEY")

    # NOTE: there is deliberately no `tara_voice_id` here any more.
    #
    # Her voice is per-LOCALE and is declared once, in
    # `voice/providers/voices.py`, where the adapter resolves it from the
    # request. One id cannot be right for three locales, and a setting beside
    # the map is a setting that silently overrides it: `services/api/.env`
    # still carried `VOICE_TARA_VOICE_ID=87748186-…`, an instrument voice from
    # M9's live-call run whose own comment said "remove after the run". With
    # `extra="ignore"` that variable is now simply unread, which is the
    # outcome we want — but it would have won over the map, on the exact
    # machine the demo runs on, if the field had survived.

    stt_model: str = "ink-whisper"
    tts_model: str = "sonic-3.5"
    timeout_seconds: float = 20.0

    #: §33.1's default. A user may hold a shorter one; nobody may hold a longer.
    retention_days: int = 30
