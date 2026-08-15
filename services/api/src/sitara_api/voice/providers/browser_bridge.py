"""A DEMO BRIDGE for Hindi listening — not a solution (CC-014, §25.3, CC-010).

What this is
------------

When `SITARA_PROTOTYPE` is active **and** the browser is Chrome, a `hi` or
`hi-Latn` call transcribes **in the browser**, through the Web Speech API, and
sends the finalised transcript up §34.6's socket as a `captions.final` — the
same frame Ink's finals already take. Nothing downstream changes: §9 receives a
user turn exactly as it does today, and every validator runs on it unmodified.

What this is NOT
----------------

**It is not the Indic streaming recogniser, and CC-010's release gate stays
OPEN.** That is enforced by construction rather than by intention:

  · `routing.CAPABILITIES` is UNTOUCHED. This module adds no cell, changes no
    cell, and is not consulted by `resolve()`. So `calls_available_in("hi")`
    still returns False, `voice.call_gate` still reads `hi`/`hi-Latn` streaming
    as BLOCKED, and `release_gates` still prints `call.indic_streaming_stt` as
    open. `tests/voice/test_browser_bridge.py` asserts every one of those.
  · The gate is a question about OUR product's capability. A demo aid that runs
    on one laptop, in one browser, against a third party's servers is not that,
    and a gate that closed on it would be reporting a capability nobody has.

Why it is acceptable at all, and only here
------------------------------------------

**Audio leaves the browser and reaches Google.** Chrome's `SpeechRecognition`
is a network service, not on-device: the microphone stream is sent to Google's
servers and a transcript comes back. That is a third-party processor nobody has
a DPA with, receiving a user's voice.

For anything beyond a local demo with synthetic personas, that violates §13
(vendor payloads, data minimisation) and §33.1 (call audio is never stored —
and never sent anywhere it could be). It is tolerable ONLY because prototype
mode is structurally confined to `environment == "dev"` on a developer machine
with seeded `+9199999` accounts, and because the screen says so while it runs.

The alternative it replaces is worse in one specific way and better in every
other: today `hi` calls simply refuse. That refusal is correct and stays the
default. This bridge exists so a Hindi call can be SHOWN, and the moment it is
unavailable the refusal comes straight back — never an English recogniser fed
Hindi audio, which is the fluent-nonsense failure CC-010 exists to prevent.
"""

from __future__ import annotations

import logging
from typing import Any

from sitara_api import prototype

logger = logging.getLogger(__name__)

#: The locales the bridge covers — exactly CC-010's gap, and nothing else.
#:
#: `en` is deliberately ABSENT. English already has a real streaming recogniser
#: (Ink), and routing it through a browser instead would replace a verified
#: vendor path with an unverified one for no reason — and would make the demo
#: stop exercising the code that actually ships.
BRIDGED_LOCALES: tuple[str, ...] = ("hi", "hi-Latn")

#: locale → the BCP-47 tag handed to `SpeechRecognition.lang`.
#:
#: Both map to `hi-IN`, and that is the honest choice rather than a shortcut:
#: Chrome has no Hinglish recogniser, and `hi-IN` fed romanised Hinglish
#: returns Devanagari. §2.4 says `hi-Latn` IS Latin script, so the bridge is
#: WRONG about script for that locale — and it is labelled as a demo bridge
#: partly for that reason. See `SCRIPT_CAVEAT`.
RECOGNISER_LANG: dict[str, str] = {
    "hi": "hi-IN",
    "hi-Latn": "hi-IN",
}

#: Stated in the code because it is the bridge's sharpest limitation, and the
#: one most likely to be mistaken for a bug during a demo.
SCRIPT_CAVEAT = (
    "hi-Latn transcripts come back in DEVANAGARI: Chrome has no Hinglish "
    "recogniser and hi-IN returns the Indic script. §2.4 makes hi-Latn a "
    "Latin-script locale, so the bridge is knowingly wrong about script there. "
    "A real Indic streaming STT (Sarvam Saaras, §3.3) is what fixes it."
)


def recogniser_for(settings: Any, locale: str) -> str | None:
    """The browser recogniser language for this locale, or None.

    **None is the answer everywhere except a prototype-mode dev machine**, and
    there is no parameter that can change that. The function takes settings and
    a locale; it has no `force`, no `allow`, no `default` and no environment
    override, because every one of those is how a demo aid reaches a user.

    `prototype.is_active` requires the switch AND `environment == "dev"`,
    checked together on every call rather than trusted from a boot-time
    assertion — a resolver that leaned on `assert_safe` having run would be one
    import away from something that never booted the app.
    """
    if not prototype.is_active(settings):
        return None
    return RECOGNISER_LANG.get(locale)


def bridges(settings: Any, locale: str) -> bool:
    """Whether the call grant should offer the bridge for this locale."""
    return recogniser_for(settings, locale) is not None
