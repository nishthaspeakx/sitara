"""Tara's voice per locale — §3.2, §2.4, CC-008.

The map itself is a product decision and not something a test can settle. What
these DO settle is the structure around it: that there is exactly one
declaration, that nothing above the adapter can carry an id, and that an
unvoiced locale declines instead of borrowing.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from sitara_api.voice.providers.base import SynthesisRequest, VoiceProviderUnavailable
from sitara_api.voice.providers.voices import TARA_VOICES, voice_for, voiced_locales

LAUNCH_LOCALES = ("en", "hi", "hi-Latn")


def test_every_launch_locale_has_a_voice() -> None:
    """§2.4 ships a language 100% or not at all, and a language Tara has no
    voice for is not shipped."""
    assert set(LAUNCH_LOCALES) <= set(TARA_VOICES)
    for locale in LAUNCH_LOCALES:
        assert voice_for(locale)


def test_hinglish_takes_the_hindi_voice_deliberately() -> None:
    """Hinglish is spoken Hindi with English words in it, so Hindi prosody is
    the right base. Asserted so that "they happen to be equal" cannot drift
    into "somebody changed one and not the other"."""
    assert TARA_VOICES["hi-Latn"] == TARA_VOICES["hi"]
    assert TARA_VOICES["en"] != TARA_VOICES["hi"]


def test_an_unvoiced_locale_declines_rather_than_borrowing() -> None:
    """The failure this prevents is not silence — it is Tara answering a Tamil
    user fluently in a Hindi woman's voice, with every metric green (CC-008)."""
    with pytest.raises(VoiceProviderUnavailable, match="no Tara voice for locale"):
        voice_for("ta")


def test_the_map_is_not_a_prefix_rule() -> None:
    """`hi-Latn`[:2] == `hi` is a COINCIDENCE here, and building on it is the
    mistake `providers/base.py` documents at length for the language map: the
    two agree at this locale for TTS and disagree for STT."""
    source = Path(inspect.getfile(voice_for)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        # `locale.split(...)`, `locale[:2]`, `partition` — any of them would be
        # deriving a voice from a language rather than reading the declaration.
        if isinstance(node, ast.Attribute) and node.attr in {"split", "partition", "removesuffix"}:
            raise AssertionError(
                "voices.py derives a locale key instead of looking it up — a "
                "prefix rule is right for hi-Latn today and wrong the moment a "
                "locale's voice differs from its language's"
            )


def test_there_is_exactly_one_declaration_of_a_voice_id() -> None:
    """No hardcoded ids above the adapter, and none beside the map.

    A UUID anywhere else in `src/` is either a second declaration or a caller
    that pinned one — both are how `en` ends up speaking with `hi`'s voice on
    one surface and not another.
    """
    import re

    uuid = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
    root = Path(inspect.getfile(voice_for)).parents[2]  # src/sitara_api
    offenders = []
    for path in root.rglob("*.py"):
        if path.name == "voices.py" or "__pycache__" in path.parts:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if uuid.search(line) and "voice" in line.lower():
                offenders.append(f"{path.relative_to(root)}:{lineno}")
    assert not offenders, (
        "voice ids outside providers/voices.py: " + ", ".join(offenders)
    )


def test_no_settings_field_can_override_the_map() -> None:
    """`VoiceSettings.tara_voice_id` is GONE, and its absence is load-bearing.

    `services/api/.env` still carries `VOICE_TARA_VOICE_ID=87748186-…` — an
    instrument voice from M9's live-call run, with a comment saying "remove
    after the run", which was never removed. A surviving field would have bound
    it and silently overridden every locale on the one machine the demo runs
    on. `Settings()` reads the ambient `.env`, which is the same trap
    `test_it_is_off_by_default` recorded for `AUTH_DEV_BYPASS`.
    """
    from sitara_api.voice.config import VoiceSettings

    assert not hasattr(VoiceSettings(), "tara_voice_id")


@pytest.mark.asyncio
async def test_the_adapter_resolves_from_the_locale_not_from_construction() -> None:
    """Two locales through ONE adapter instance must reach two voices. An
    adapter holding a single id could not, and that is exactly what it held."""
    import httpx

    from sitara_api.voice.providers.cartesia import CartesiaTtsProvider

    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen.append(json.loads(request.content)["voice"]["id"])
        return httpx.Response(200, content=b"\x00\x01" * 100)

    transport = httpx.MockTransport(handler)
    real = httpx.AsyncClient

    def factory(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        kwargs["transport"] = transport
        return real(*args, **kwargs)

    provider = CartesiaTtsProvider("sk_test")
    import unittest.mock

    with unittest.mock.patch("httpx.AsyncClient", factory):
        for locale in LAUNCH_LOCALES:
            await provider.synthesise(SynthesisRequest(text="hello", locale=locale))

    assert seen == [TARA_VOICES[loc] for loc in LAUNCH_LOCALES]
    assert len(set(seen)) == 2  # en distinct; hi and hi-Latn shared


def test_voiced_locales_is_sorted_and_complete() -> None:
    assert voiced_locales() == tuple(sorted(TARA_VOICES))
