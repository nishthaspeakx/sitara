"""Per-language STT routing (§3.3, §25.3, CC-010).

The ruling this file exists to make unrepresentable
---------------------------------------------------

Cartesia Ink's **streaming** endpoint recognises English only; its batch
endpoint carries 49 languages. Voice notes use batch — a note is a complete
recording — so all three launch locales work there. A live call cannot use
batch, so `hi` and `hi-Latn` live calls have no recogniser at all today.

**An English model fed Hindi audio does not fail. It produces fluent, confident
English nonsense**, which then reaches §9 as the user's question and gets
answered seriously. That is the failure mode this product least tolerates: not
a decline, not an error state, but a plausible answer to a question nobody
asked. Every other guard in this codebase — cite-or-die, the entity check, the
grounding validator — sits *downstream* of the transcript and cannot see it,
because they all gate what Tara says and this fabrication is on the user's side
of the turn.

So the routing is a lookup that can return NOTHING, and "nothing" is a designed
state rather than an error:

    resolve(Modality.STREAMING, "hi")  -> Route(provider=None, reason=...)

There is deliberately no fallback parameter, no `or CARTESIA`, and no default
argument anywhere in this module. A silent fallback is the whole defect, and
the way it gets reintroduced is someone adding a sensible-looking default to a
function that had none.

Why a capability MATRIX rather than an if-statement
---------------------------------------------------

§3.2 requires engineering to build against adapters so a bake-off can swap a
provider by configuration. The thing that actually has to change when Sarvam's
realtime arm lands is one cell of `CAPABILITIES` — from `declared` to
`implemented` — plus an adapter class. Not a refactor, not a new branch in a
router, and nothing in the call screen: the screen already asks
`calls_available_in(locale)` and will simply start getting `True`.

CC-010 defers Sarvam. It stays DECLARED here, which is what makes that one-cell
change true rather than aspirational — and what makes the gap visible in
`/shipcheck` instead of living in someone's head.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

from sitara_api.voice.providers.base import VoiceProviderName

logger = logging.getLogger(__name__)


class Modality(StrEnum):
    """How audio reaches the recogniser, which is what decides availability.

    Not a detail: the same vendor, the same language and the same model can be
    available in one modality and absent in the other, which is exactly the
    situation §25.3 is in today.
    """

    #: A complete recording, transcribed after the fact (§25.4's voice notes).
    BATCH = "batch"
    #: A live socket, transcribed as it arrives (§25.3's calls).
    STREAMING = "streaming"


class Support(StrEnum):
    """What we can honestly say about a (provider, modality, language) cell."""

    #: Verified against the live API, with a recorded fixture behind it.
    IMPLEMENTED = "implemented"
    #: The vendor documents it; no adapter is written. Cannot serve traffic.
    DECLARED = "declared"
    #: The vendor does not offer it. Not a gap to be closed by us.
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class Route:
    """The answer, including when the answer is "no one".

    `reason` is a message KEY, not a sentence: §2.4 puts every user-facing
    string in the catalogs, and this reason reaches a screen.
    """

    provider: VoiceProviderName | None
    support: Support
    reason_key: str | None = None

    @property
    def available(self) -> bool:
        return self.provider is not None


#: (provider, modality) → {locale: Support}
#:
#: Verified live on 13 Aug 2026 for Cartesia. Sarvam's row is what the vendor
#: documents (§3.1: "Saaras v3 STT with explicit code-mix (Hinglish)
#: preservation"), and every cell is DECLARED because no live call has been
#: made against it — the same honesty `panchang/providers` keeps between
#: Prokerala (verified) and DivineAPI (unverified).
CAPABILITIES: dict[tuple[VoiceProviderName, Modality], dict[str, Support]] = {
    (VoiceProviderName.CARTESIA, Modality.BATCH): {
        # Ink's batch endpoint: 49 languages including hi. This is what makes
        # §25.4's voice notes work in all three locales today.
        "en": Support.IMPLEMENTED,
        "hi": Support.IMPLEMENTED,
        "hi-Latn": Support.IMPLEMENTED,
    },
    (VoiceProviderName.CARTESIA, Modality.STREAMING): {
        "en": Support.IMPLEMENTED,
        # The vendor's own docs: `language` on the STT websocket is "currently
        # only `en` supported". Not a gap we can close by writing code.
        "hi": Support.UNSUPPORTED,
        "hi-Latn": Support.UNSUPPORTED,
    },
    (VoiceProviderName.SARVAM, Modality.BATCH): {
        "en": Support.DECLARED,
        "hi": Support.DECLARED,
        "hi-Latn": Support.DECLARED,
    },
    (VoiceProviderName.SARVAM, Modality.STREAMING): {
        # §3.3 makes Saaras Hinglish's PRIMARY STT, and this is the cell that
        # unblocks hi/hi-Latn calls. DECLARED → IMPLEMENTED plus an adapter is
        # the entire change; `release_gates` watches this exact cell.
        "en": Support.DECLARED,
        "hi": Support.DECLARED,
        "hi-Latn": Support.DECLARED,
    },
}

#: Preference order per modality. Cartesia first per CC-009/CC-010; Sarvam is
#: consulted and — being DECLARED, not IMPLEMENTED — never selected, which is
#: what keeps this list honest rather than decorative.
PREFERENCE: tuple[VoiceProviderName, ...] = (
    VoiceProviderName.CARTESIA,
    VoiceProviderName.SARVAM,
)


def resolve(modality: Modality, locale: str) -> Route:
    """Which provider may transcribe this locale in this modality.

    Returns a Route with `provider=None` when none may. That is a designed
    state — §25.3's call affordance reads it and hides itself — and it is the
    only correct answer for `hi`/`hi-Latn` streaming today.
    """
    best = Support.UNSUPPORTED
    for provider in PREFERENCE:
        support = CAPABILITIES.get((provider, modality), {}).get(locale, Support.UNSUPPORTED)
        if support is Support.IMPLEMENTED:
            return Route(provider=provider, support=support)
        if support is Support.DECLARED:
            best = Support.DECLARED

    if best is Support.DECLARED:
        # A provider documents it and nobody has built it. Honest, and distinct
        # from "impossible" — this is the state a gate should be watching.
        return Route(
            provider=None,
            support=Support.DECLARED,
            reason_key="errors.voice.call_language_pending",
        )
    return Route(
        provider=None,
        support=Support.UNSUPPORTED,
        reason_key="errors.voice.call_language_unavailable",
    )


def calls_available_in(locale: str) -> bool:
    """§25.3's affordance gate.

    The call button asks this. It is a single function so that "calls do not
    work in Hindi yet" is one fact with one implementation, rather than a
    condition repeated across a screen, a router and a socket — the three
    places it would drift between.
    """
    return resolve(Modality.STREAMING, locale).available


def voice_notes_available_in(locale: str) -> bool:
    """§25.4's affordance gate. Separate from calls ON PURPOSE.

    CC-010: voice notes stay available in all three languages via the batch
    endpoint while calls do not. Collapsing these into one "voice works"
    boolean would take voice notes down in hi and hi-Latn for a limitation
    that has nothing to do with them.
    """
    return resolve(Modality.BATCH, locale).available


def blocked_locales(modality: Modality, locales: tuple[str, ...]) -> tuple[str, ...]:
    """Which of `locales` have no recogniser. Read by the release gate."""
    return tuple(loc for loc in locales if not resolve(modality, loc).available)
