"""S12's voice preview — §29.1, §0.11 item 11, §2.4-6, §3.4.

The behaviour is small: Tara says a name. The tests that matter are the ones
about what CANNOT reach the synthesiser through this door, because that is the
property the module was shaped around and the one no downstream validator can
recover if it is lost.
"""

from __future__ import annotations

import inspect

import pytest

from sitara_api.localisation import SERVER_RENDERED_KEYS, resolve
from sitara_api.voice import preview
from sitara_api.voice.providers.base import (
    SynthesisRequest,
    SynthesisResult,
    VoiceProviderName,
    VoiceProviderUnavailable,
)

pytestmark = pytest.mark.asyncio

LOCALES = ("en", "hi", "hi-Latn")


class RecordingTts:
    """Captures exactly what was handed to the vendor."""

    name = VoiceProviderName.CARTESIA

    def __init__(self) -> None:
        self.requests: list[SynthesisRequest] = []

    async def synthesise(self, request: SynthesisRequest) -> SynthesisResult:
        self.requests.append(request)
        return SynthesisResult(
            audio=b"\x00\x01" * 8_000,
            sample_rate_hz=16_000,
            provider=self.name,
            model="sonic-2",
            voice_id=request.voice_id,
        )


def profile(**block) -> dict:  # noqa: ANN003
    return {"name_pronunciation": block}


# ---------------------------------------------------------------------------
# The guarantee
# ---------------------------------------------------------------------------


async def test_synthesise_preview_has_no_parameter_a_draft_could_arrive_through() -> None:
    """Structural, not behavioural — the guarantee is the SIGNATURE.

    Exactly `speak_holding_phrase`'s test, on the second surface that needs
    arbitrary-looking words synthesised. A `text` parameter here would let a
    route hand the synthesiser a model draft, and the audio would carry a
    sentence grounding never saw. Checking today's behaviour instead would pass
    the day somebody adds the parameter "just for the tests".
    """
    params = inspect.signature(preview.synthesise_preview).parameters
    assert set(params) == {"tts", "locale", "profile", "environment"}, (
        "synthesise_preview grew a parameter — if it can carry text, a model "
        "draft can reach the synthesiser without passing a single validator"
    )


async def test_the_route_has_no_body_or_query_carrying_text() -> None:
    """The signature guarantee is worthless if the ROUTE takes text and calls
    something else with it. This asserts the door as well as the room."""
    from sitara_api.voice.router import get_voice_preview

    params = inspect.signature(get_voice_preview).parameters
    assert set(params) == {"request", "session"}


async def test_the_spoken_line_is_a_catalog_key_verified_at_boot() -> None:
    """§2.4 has no English fallback, so a missing Hindi line would be Tara
    introducing herself in the wrong language at the first moment the product
    speaks. That has to fail at boot, not at the microphone."""
    assert preview.PREVIEW_LINE_KEY in SERVER_RENDERED_KEYS
    for locale in LOCALES:
        assert "{name}" in resolve(preview.PREVIEW_LINE_KEY, locale)


# ---------------------------------------------------------------------------
# The two names
# ---------------------------------------------------------------------------


async def test_it_says_the_display_name_when_there_is_no_override() -> None:
    tts = RecordingTts()
    await preview.synthesise_preview(
        tts, locale="en", profile=profile(display_name="Asha")
    )
    assert "Asha" in tts.requests[0].text


async def test_the_override_is_spoken_and_the_display_name_is_not() -> None:
    """§2.4-6's whole point: she says it the way it SOUNDS. §3.4's rule is what
    keeps the respelling out of everything that is read rather than heard —
    tested from the other side in `test_the_override_never_leaves_the_synthesiser`."""
    tts = RecordingTts()
    await preview.synthesise_preview(
        tts,
        locale="en",
        profile=profile(display_name="Asha", override="Uh-SHA"),
    )
    spoken = tts.requests[0].text
    assert "Uh-SHA" in spoken
    assert "Asha" not in spoken


async def test_the_override_never_leaves_the_synthesiser() -> None:
    """The profile document is untouched by speaking. An override that got
    written back over `display_name` would put a stranger's spelling of
    someone's own name into their own thread and their own brief."""
    doc = profile(display_name="Asha", override="Uh-SHA")
    before = {**doc["name_pronunciation"]}
    await preview.synthesise_preview(RecordingTts(), locale="en", profile=doc)
    assert doc["name_pronunciation"] == before


async def test_a_blank_override_falls_back_rather_than_saying_nothing() -> None:
    tts = RecordingTts()
    await preview.synthesise_preview(
        tts, locale="en", profile=profile(display_name="Asha", override="   ")
    )
    assert "Asha" in tts.requests[0].text


# ---------------------------------------------------------------------------
# Locale
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("locale", LOCALES)
async def test_she_introduces_herself_in_the_accounts_own_language(locale: str) -> None:
    tts = RecordingTts()
    await preview.synthesise_preview(
        tts, locale=locale, profile=profile(display_name="Asha")
    )
    request = tts.requests[0]
    assert request.locale == locale
    # The line is the catalog's, with the name substituted — not a translation
    # invented here and not English standing in for a missing locale (§2.4).
    assert request.text == resolve(preview.PREVIEW_LINE_KEY, locale).replace(
        "{name}", "Asha"
    )


async def test_hinglish_is_not_hindi() -> None:
    """`hi-Latn` IS Hinglish, in Latin script. The locale is carried through to
    the request rather than being prefix-reduced to `hi` — the map in
    `providers/base.py` is what decides the vendor language, and it differs
    between the two at exactly this locale."""
    tts = RecordingTts()
    await preview.synthesise_preview(
        tts, locale="hi-Latn", profile=profile(display_name="Meera")
    )
    assert tts.requests[0].locale == "hi-Latn"


# ---------------------------------------------------------------------------
# Declining
# ---------------------------------------------------------------------------


async def test_no_synthesiser_declines_rather_than_returning_silence() -> None:
    """§30.1: S12 has a designed unavailable state. A zero-length WAV would be
    a player that plays nothing and says everything is fine."""
    with pytest.raises(VoiceProviderUnavailable):
        await preview.synthesise_preview(
            None, locale="en", profile=profile(display_name="Asha")
        )


@pytest.mark.parametrize("doc", [None, {}, profile(), profile(display_name="  ")])
async def test_no_name_declines(doc) -> None:  # noqa: ANN001
    """S12 is reachable before S10 in a resumed onboarding. A preview of the
    empty string is a request to decline, not a recording to make."""
    with pytest.raises(VoiceProviderUnavailable):
        await preview.synthesise_preview(RecordingTts(), locale="en", profile=doc)


# ---------------------------------------------------------------------------
# §3.4
# ---------------------------------------------------------------------------


async def test_pronunciation_overrides_are_applied_on_the_way_in() -> None:
    """The dictionary reaches the synthesiser here for the same reason it does
    in `_synthesise_reply` — this is a way IN, and §3.4 says every way in
    applies it. Asserted through the module's real policy file rather than a
    stub, so a locale losing its dictionary shows up here."""
    from sitara_api.voice import pronunciation

    tts = RecordingTts()
    await preview.synthesise_preview(
        tts, locale="en", profile=profile(display_name="Asha"), environment="dev"
    )
    line = resolve(preview.PREVIEW_LINE_KEY, "en").replace("{name}", "Asha")
    assert tts.requests[0].text == pronunciation.apply(line, "en", environment="dev")
