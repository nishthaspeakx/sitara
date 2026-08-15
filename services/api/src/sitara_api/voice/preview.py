"""S12's voice preview — Tara says the user's name (§29.1, §0.11 item 11, §2.4-6).

§0.11 describes this screen in one line: "hear Tara say the user's name
(pronunciation confirm/fix — stores override), choose voice on/off default".
Every clause of that is a moving part, and the one that dictates this module's
shape is the FIRST one.

**Nothing here takes text from a caller, and that is the guarantee.**

This is the same rule `CallTurnService.speak_holding_phrase` is built around,
and it applies here for the same reason. §25.4's `speak()` is safe because it
can only ever read `turn.text` — the presented, validated turn — and
`tests/voice/test_grounding_parity.py` asserts that from outside. A preview
needs arbitrary-looking words synthesised, which is exactly the shape that
undoes it: one `synthesise(text: str)` reachable from a route and a future
caller can hand the synthesiser a model draft, with audio carrying the sentence
grounding REJECTED while the screen shows the one it accepted. No validator
downstream can see that difference, because by the time grounding runs the
draft is already at the vendor.

So there is no text parameter anywhere in this module or on the route above it.
The sentence comes from the catalogs by KEY, resolved in the account's own
locale, and the only thing that varies is the user's own NAME — which is not a
claim about the world, and is the entire point of the screen.

Two names, and they are not the same name
-----------------------------------------

`display_name` is what the user is CALLED — it is written in their thread, in
their brief, and on this screen. `override` is §2.4-6's per-user phonetic
override: "if a name is new, Tara asks once, in-locale, how to say it, and
stores the phonetic override in the user's profile". §3.4's rule then binds it
exactly as it binds every other respelling — **it reaches the synthesiser and
nothing else**. An override that leaked into a transcript would put a
stranger's spelling of someone's own name into their own thread, which is a
worse version of the "raahoo kaal" failure §3.4 exists to prevent, because it
is their name.

The field is `name_pronunciation.override` and NOT a new one. `db/seed.py` has
declared exactly that key since M4 and nothing had ever read or written it —
so the obvious move, inventing `spoken_as` beside it, would have left the
schema carrying two fields for one concept with the seeder populating the dead
one. That is the shape M8-P10 found twice (two `PresenceState` twelves, two
memory-type elevens) and it is cheaper to not create than to reconcile.
"""

from __future__ import annotations

import logging

from sitara_api.localisation import resolve
from sitara_api.voice import pronunciation
from sitara_api.voice.providers.base import (
    SynthesisRequest,
    SynthesisResult,
    TtsProvider,
    VoiceProviderUnavailable,
)

logger = logging.getLogger(__name__)

#: The one sentence this screen synthesises. A KEY, never a string a caller
#: supplies — see the module docstring. It carries a single `{name}` slot, and
#: `verify_catalogs` proves it resolves in every launch locale at BOOT, because
#: §2.4 has no English fallback and a missing Hindi line here would be Tara
#: introducing herself in the wrong language at the one moment the product is
#: making its first promise about language.
PREVIEW_LINE_KEY = "start.voice.preview_line"


def spoken_name(profile: dict | None) -> str | None:
    """The name to SYNTHESISE, which is not always the name to display.

    Returns None when there is no name at all — S12 is reachable before S10 in
    a resumed onboarding, and a preview of the empty string is a request worth
    declining rather than a recording of Tara saying nothing.
    """
    block = (profile or {}).get("name_pronunciation") or {}

    def usable(value: object) -> str | None:
        # Stripped BEFORE the fallback decision, not after. A whitespace-only
        # override is truthy, so testing it raw shadows the display name and
        # then collapses to nothing — the preview declines for a user who has a
        # perfectly good name, because of a field they left blank.
        return value.strip() or None if isinstance(value, str) else None

    # §2.4-6's override wins for SPEECH only. `display_name` remains what every
    # other surface reads.
    return usable(block.get("override")) or usable(block.get("display_name"))


async def synthesise_preview(
    tts: TtsProvider | None,
    *,
    locale: str,
    profile: dict | None,
    environment: str = "dev",
) -> SynthesisResult:
    """Tara's preview line, spoken in `locale`, with this user's name in it.

    Raises `VoiceProviderUnavailable` when there is no synthesiser or no name.
    The route turns that into §34.4's `VOICE_PROVIDER_UNAVAILABLE`, and S12
    renders the honest unavailable state it has carried since M8 — which is a
    designed state, not a broken screen (§30.1).
    """
    if tts is None:
        raise VoiceProviderUnavailable("no TTS configured (§3.2)")

    name = spoken_name(profile)
    if name is None:
        raise VoiceProviderUnavailable("no name to say yet (§29.1 S10 precedes S12)")

    # §2.4: `resolve` raises rather than falling across a language family, and
    # boot has already proved this key resolves everywhere. A raise here means
    # a catalog changed under a running process.
    line = resolve(PREVIEW_LINE_KEY, locale).replace("{name}", name)

    # §3.4, the single call site rule: respellings are applied on the way INTO
    # the synthesiser and nowhere else. Note this runs over the composed line,
    # so the dictionary's tradition terms and the user's own name are handled
    # by one pass rather than two competing ones.
    spoken = pronunciation.apply(line, locale, environment=environment)

    return await tts.synthesise(
        SynthesisRequest(text=spoken, locale=locale)
    )
