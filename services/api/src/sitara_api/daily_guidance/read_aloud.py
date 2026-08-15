"""S14's morning brief, read aloud (§27, §24.3's AudioPlayer, §3.4).

`AudioPlayer`'s own docstring has called itself "the morning-brief player on
S14" since M7, and until now nothing produced audio for it to play:
`daily_briefings.audio_ref` was declared in §6.4, written by the store, read
back by the store, and never once set — a field with two readers and no writer.

**Nothing here takes text from a caller.** The sentences are the brief's own
`rendered` text, which the ranking engine composed from facts and which already
passed §9's grounding before it was stored. That is the same rule
`voice/preview.py` and `speak_holding_phrase` are built on, and it matters more
here than on either: a brief is the surface with the most astrological claims
per sentence in the product, so a `text` parameter on this route would be the
shortest path from an unvalidated string to a user's ear.

§27 makes briefs listen-only, which is why this is one rendering of the whole
brief rather than a per-card player: there is no seek target a card would give
you that the transcript below it does not give you better.
"""

from __future__ import annotations

import logging

from sitara_api.daily_guidance.types import Brief
from sitara_api.voice import pronunciation
from sitara_api.voice.providers.base import (
    SynthesisRequest,
    SynthesisResult,
    TtsProvider,
    VoiceProviderUnavailable,
)

logger = logging.getLogger(__name__)

#: Between the date line, Tara's line and each card. Two newlines rather than
#: one: Sonic reads a paragraph break as a longer pause than a line break, and
#: §0.9's "unhurried" is carried by pacing more than by anything else available
#: — the vendor ignores `speed` entirely (see `providers/cartesia.py`).
_JOIN = "\n\n"


def brief_script(brief: Brief) -> str:
    """The words to speak, in reading order, from the brief itself.

    Tara's line first, then each card — the order S14 renders, because a brief
    read in a different order from the one on screen is a second composition
    and would need its own §9 pass to be safe.
    """
    parts: list[str] = []
    for module in brief.modules:
        text = module.rendered.strip()
        if text:
            parts.append(text)
    return _JOIN.join(parts)


async def synthesise_brief(
    tts: TtsProvider | None,
    brief: Brief,
    *,
    environment: str = "dev",
) -> SynthesisResult:
    """Read `brief` aloud in its OWN locale.

    `brief.locale`, never the request's: §32.13 stores the locale the brief was
    COMPOSED in, and a brief composed in Hindi read by the English voice would
    be the §2.4 failure the locale field exists to prevent — the same one
    `POST /auth/session` was fixed for in M10, one surface over.
    """
    if tts is None:
        raise VoiceProviderUnavailable("no TTS configured (§3.2)")

    script = brief_script(brief)
    if not script:
        # A brief with no composed modules is a real state (§7.1's FAILED, and
        # the first-session variant). There is nothing to read, and silence
        # with a play button over it would be worse than no player.
        raise VoiceProviderUnavailable("this brief has no composed text to read")

    # §3.4's single call site rule, on the way INTO the synthesiser and nowhere
    # else. The stored brief keeps its real words: a respelling that reached
    # `daily_briefings` would put "raahoo kaal" in the Journal for ever.
    spoken = pronunciation.apply(script, brief.locale, environment=environment)

    return await tts.synthesise(SynthesisRequest(text=spoken, locale=brief.locale))
