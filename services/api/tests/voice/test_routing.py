"""Per-language STT routing (§3.3, §25.3, CC-010).

The ruling: hi and hi-Latn live calls are EXPLICITLY UNAVAILABLE, never
silently routed to an English recogniser. These tests hold that line from
outside, because the failure it prevents is invisible from inside — an English
model fed Hindi audio does not error, it produces fluent nonsense, and every
validator downstream gates what Tara says rather than what the transcript
claims the user said.
"""

from __future__ import annotations

import pytest

from sitara_api.voice.providers.base import VoiceProviderName
from sitara_api.voice.providers.routing import (
    CAPABILITIES,
    PREFERENCE,
    Modality,
    Support,
    blocked_locales,
    calls_available_in,
    resolve,
    voice_notes_available_in,
)

LAUNCH = ("en", "hi", "hi-Latn")


# --------------------------------------------------------------------------
# The ruling


def test_indic_live_calls_resolve_to_NO_provider() -> None:
    """The headline. Not a fallback, not a degraded provider — nobody.

    If this ever returns a provider for hi or hi-Latn, check what it is: the
    only correct way for it to change is Sarvam's streaming cell going
    IMPLEMENTED with an adapter behind it.
    """
    for locale in ("hi", "hi-Latn"):
        route = resolve(Modality.STREAMING, locale)
        assert route.provider is None, locale
        assert not route.available
        assert route.reason_key  # the screen has something honest to say


def test_english_live_calls_route_to_cartesia() -> None:
    route = resolve(Modality.STREAMING, "en")
    assert route.provider is VoiceProviderName.CARTESIA
    assert route.support is Support.IMPLEMENTED


def test_voice_notes_stay_available_in_all_three() -> None:
    """CC-010 keeps these separate on purpose. A single "voice works" boolean
    would take voice notes down in hi and hi-Latn for a streaming limitation
    that has nothing to do with them."""
    for locale in LAUNCH:
        assert voice_notes_available_in(locale), locale
        assert resolve(Modality.BATCH, locale).provider is VoiceProviderName.CARTESIA


def test_calls_and_notes_disagree_exactly_where_they_should() -> None:
    assert [calls_available_in(loc) for loc in LAUNCH] == [True, False, False]
    assert [voice_notes_available_in(loc) for loc in LAUNCH] == [True, True, True]


def test_a_declared_provider_is_never_selected() -> None:
    """Sarvam is in the preference list and documents every cell. Being
    DECLARED rather than IMPLEMENTED, it must never serve traffic — otherwise
    "declared" would mean "used", and the bake-off would have already happened
    by accident."""
    assert VoiceProviderName.SARVAM in PREFERENCE
    for modality in Modality:
        for locale in LAUNCH:
            route = resolve(modality, locale)
            assert route.provider is not VoiceProviderName.SARVAM, (modality, locale)


def test_declared_and_unsupported_are_different_answers() -> None:
    """"a vendor offers it and we have not built it" is a gate's problem;
    "no vendor offers it" is not. Collapsing them would make the release gate
    unable to say which one it is waiting for."""
    pending = resolve(Modality.STREAMING, "hi")
    assert pending.support is Support.DECLARED
    assert pending.reason_key == "errors.voice.call_language_pending"

    unknown = resolve(Modality.STREAMING, "ta")
    assert unknown.support is Support.UNSUPPORTED
    assert unknown.reason_key == "errors.voice.call_language_unavailable"


def test_an_unmapped_locale_is_unavailable_rather_than_defaulted() -> None:
    """§2.4: no silent fallback, ever. The five §3.3 languages M9 does not
    serve must come back unavailable, not routed to English."""
    for absent in ("ta", "te", "gu", "mr", "pa", "bn"):
        assert not calls_available_in(absent), absent
        assert not voice_notes_available_in(absent), absent


# --------------------------------------------------------------------------
# The shape that makes Sarvam a config change rather than a refactor


def test_landing_sarvam_streaming_is_ONE_cell() -> None:
    """CC-010: "adding it later is a config change and one implementation, not
    a refactor". This asserts that literally — flip the cell, and hi/hi-Latn
    calls become available with nothing else touched.

    The mutation is undone in a finally block: a leaked capability change would
    make every other test in this file pass for the wrong reason.
    """
    cell = (VoiceProviderName.SARVAM, Modality.STREAMING)
    before = dict(CAPABILITIES[cell])
    try:
        CAPABILITIES[cell] = {loc: Support.IMPLEMENTED for loc in LAUNCH}
        assert calls_available_in("hi")
        assert resolve(Modality.STREAMING, "hi").provider is VoiceProviderName.SARVAM
        # English still prefers Cartesia — the preference order decides, and
        # landing Sarvam must not silently move English off a verified arm.
        assert resolve(Modality.STREAMING, "en").provider is VoiceProviderName.CARTESIA
    finally:
        CAPABILITIES[cell] = before

    assert not calls_available_in("hi"), "the capability mutation leaked"


def test_the_gate_can_name_what_is_blocked() -> None:
    assert blocked_locales(Modality.STREAMING, LAUNCH) == ("hi", "hi-Latn")
    assert blocked_locales(Modality.BATCH, LAUNCH) == ()


def test_resolve_has_no_fallback_parameter() -> None:
    """The defect this module exists to prevent gets reintroduced by someone
    adding a sensible-looking default. There is no parameter here that could
    carry one, and this asserts the signature stays that way."""
    import inspect

    params = inspect.signature(resolve).parameters
    assert list(params) == ["modality", "locale"]
    assert all(p.default is inspect.Parameter.empty for p in params.values())


@pytest.mark.parametrize("locale", LAUNCH)
def test_every_launch_locale_has_an_explicit_cell(locale: str) -> None:
    """A locale missing from the matrix resolves to UNSUPPORTED, which is safe
    but silent. §2.4's locales should be stated, so a reader can see what was
    decided rather than inferring it from an absence."""
    for provider in PREFERENCE:
        for modality in Modality:
            assert locale in CAPABILITIES[(provider, modality)], (provider, modality)
