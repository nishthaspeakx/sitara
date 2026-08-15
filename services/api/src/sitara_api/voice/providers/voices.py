"""Tara's VOICE per locale — the one declaration (§3.2, §3.3, §2.4, CC-008).

This file is the only place a Cartesia voice id appears. Nothing above the
adapter names one, holds one, or can pass one down: `SynthesisRequest.voice_id`
exists as a per-request OVERRIDE for a bake-off harness, and every production
caller leaves it None so the voice is resolved HERE, from the locale.

── Why one map and not one id ─────────────────────────────────────────────────

`VoiceSettings.tara_voice_id` used to be a single string threaded from settings
through the registry into every adapter, and through `app.py`, `voice/router.py`,
`calls/service.py`, `voice/service.py` and `voice/preview.py` on the way. One id
cannot be right for three locales, and the threading meant six files knew about
a value none of them had any business holding. Both problems go away by asking
the locale instead.

It also removed a live trap: `services/api/.env` carried
`VOICE_TARA_VOICE_ID=87748186-…`, an INSTRUMENT voice from M9's live-call
verification with a comment saying "remove after the run". It was never removed.
Any per-locale map added beside a surviving `tara_voice_id` would have been
silently overridden by it on the developer machine where the demo runs — the
exact shape of the `Settings()`-reads-ambient-.env lesson the M10 walkthrough
already recorded, one field over.

── Why hi-Latn takes the HINDI voice ──────────────────────────────────────────

`providers/base.py` states the rule this file follows: a locale is not a
language code, and `hi-Latn` differs from `hi` for STT (Latin script) while
agreeing with it for TTS. The voice map agrees with the TTS map for the same
reason the TTS map says so — **Hinglish is spoken Hindi with English words in
it**, so Hindi prosody is the correct base and an English voice reading
Hinglish puts an English speaker's rhythm on Hindi sentence structure.

That is a judgement about how she should SOUND, and it is the one thing in this
module that cannot be settled by a test. `scripts/compare_voices.py` renders the
same sentences through all three so it can be settled by ear.

── One woman, three languages ─────────────────────────────────────────────────

§3.2's architecture is "one personality, anchor clone for EN/Hinglish/HI". Two
ids across three locales is the closest this repo can get to that today, and it
is not the same thing as a verified anchor clone: `en` and `hi` are two separate
Cartesia voices, not one voice speaking two languages. Whether they read as the
same woman is exactly what the comparison script exists to answer, and §3.2's
acceptance gate remains FINAL and NOT MET either way.
"""

from __future__ import annotations

from sitara_api.voice.providers.base import VoiceProviderUnavailable

#: locale → Cartesia Sonic voice id. THE declaration.
#:
#: Adding a locale is one row here plus the §12 admin locale gate — never a
#: fallback, and never a prefix rule (`hi-Latn`[:2] would be a coincidence that
#: happens to work here and breaks the moment a locale's voice differs from its
#: language's).
TARA_VOICES: dict[str, str] = {
    "en": "f8f5f1b2-f02d-4d8e-a40d-fd850a487b3d",
    "hi": "faf0731e-dfb9-4cfc-8119-259a79b27e12",
    # Deliberately the Hindi voice. See the header.
    "hi-Latn": "faf0731e-dfb9-4cfc-8119-259a79b27e12",
}


def voice_for(locale: str) -> str:
    """Tara's voice in this locale, or a refusal.

    §2.4 admits a locale only through the §12 gate, so an unmapped locale
    DECLINES rather than borrowing a neighbour's voice. The failure mode that
    rule prevents is not silence — it is Tara answering a Tamil user in a Hindi
    woman's voice, fluently, with every accuracy metric green.
    """
    try:
        return TARA_VOICES[locale]
    except KeyError:
        raise VoiceProviderUnavailable(
            f"no Tara voice for locale {locale!r} (§2.4, §3.2) — a locale without "
            "a cast voice declines; borrowing another locale's voice would put a "
            "stranger's voice on her name (CC-008)"
        ) from None


def voiced_locales() -> tuple[str, ...]:
    """The locales Tara can speak in. Read by the comparison script and by
    anything that wants to report coverage without importing the map."""
    return tuple(sorted(TARA_VOICES))
