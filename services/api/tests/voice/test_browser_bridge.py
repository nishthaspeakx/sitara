"""CC-014's demo bridge — and the four things it must not become.

The bridge itself is twenty lines. These tests are the reason it is safe to
have at all, and they are all NEGATIVES: what it cannot do, where it cannot
reach, and which gate it must never close.
"""

from __future__ import annotations

import inspect

import pytest

from sitara_api.voice.providers import browser_bridge
from sitara_api.voice.providers.routing import (
    CAPABILITIES,
    Modality,
    Support,
    calls_available_in,
    resolve,
)

INDIC = ("hi", "hi-Latn")


class Settings:
    """Just the two fields `prototype.is_active` reads."""

    def __init__(self, *, prototype_mode: bool, environment: str) -> None:
        self.prototype_mode = prototype_mode
        self.environment = environment


DEV_ON = Settings(prototype_mode=True, environment="dev")
DEV_OFF = Settings(prototype_mode=False, environment="dev")


# ---------------------------------------------------------------------------
# 1. Structurally impossible outside prototype mode
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("environment", ["prod", "staging", "beta", "test", "local", ""])
@pytest.mark.parametrize("locale", INDIC)
def test_no_environment_but_dev_can_reach_the_bridge(environment: str, locale: str) -> None:
    """Both halves are checked on EVERY call, not trusted from boot.

    `prototype_mode=True` with a non-dev environment is exactly the shape an
    operator produces by copying a `.env`, and it must answer None.
    """
    settings = Settings(prototype_mode=True, environment=environment)
    assert browser_bridge.recogniser_for(settings, locale) is None
    assert browser_bridge.bridges(settings, locale) is False


@pytest.mark.parametrize("locale", INDIC)
def test_the_switch_alone_is_not_enough_either(locale: str) -> None:
    assert browser_bridge.recogniser_for(DEV_OFF, locale) is None


def test_there_is_no_parameter_that_could_force_it_on() -> None:
    """A refusal, not a config default — so the signature must have nowhere for
    an override to live. `force=`, `allow=`, `default=` are each how a demo aid
    reaches a user, and none of them can be added without failing here."""
    params = inspect.signature(browser_bridge.recogniser_for).parameters
    assert set(params) == {"settings", "locale"}
    assert all(p.default is inspect.Parameter.empty for p in params.values())


def test_it_is_on_in_prototype_dev_which_is_the_whole_point() -> None:
    for locale in INDIC:
        assert browser_bridge.recogniser_for(DEV_ON, locale) == "hi-IN"


# ---------------------------------------------------------------------------
# 2. CC-010's gate stays OPEN and completely unchanged
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("locale", INDIC)
def test_the_capability_matrix_is_untouched(locale: str) -> None:
    """The bridge adds NO cell. This is the assertion the whole design exists
    to make true: a cell here would close a gate on a capability nobody has."""
    from sitara_api.voice.providers.base import VoiceProviderName

    cell = CAPABILITIES[(VoiceProviderName.CARTESIA, Modality.STREAMING)][locale]
    assert cell is Support.UNSUPPORTED
    assert CAPABILITIES[(VoiceProviderName.SARVAM, Modality.STREAMING)][locale] is Support.DECLARED


@pytest.mark.parametrize("locale", INDIC)
def test_calls_are_still_unavailable_in_hindi(locale: str) -> None:
    """`calls_available_in` is the single implementation of CC-010's fact, and
    the bridge must not have moved it."""
    assert calls_available_in(locale) is False
    assert resolve(Modality.STREAMING, locale).provider is None


@pytest.mark.parametrize("locale", INDIC)
def test_the_release_gate_still_reads_blocked(locale: str) -> None:
    """§33.5's two blocked measures read the routing matrix so they unblock on
    the commit that unblocks them. A demo bridge must not be that commit."""
    from sitara_api.voice.call_gate import evaluate

    table = evaluate()
    assert table.passes is False
    assert table.blocked, "the two CC-010 measures should still be BLOCKED"


def test_the_indic_streaming_release_gate_is_still_open() -> None:
    from sitara_api.release_gates import gates

    gate = next(g for g in gates() if g.id == "call.indic_streaming_stt")
    assert gate.status != "closed", gate.status
    assert "hi" in gate.detail


def test_the_bridge_is_not_reachable_from_resolve() -> None:
    """`resolve()` is what the gate, the affordance and the socket all read.
    The bridge is asked separately, by name, in exactly one place — if it ever
    became a route, every one of those would silently start believing it."""
    source = inspect.getsource(resolve)
    assert "browser" not in source.lower()
    assert "bridge" not in source.lower()


# ---------------------------------------------------------------------------
# 3. Never a silent degrade to an English recogniser
# ---------------------------------------------------------------------------


def test_english_is_not_bridged() -> None:
    """`en` has a real recogniser. Bridging it would swap a verified vendor
    path for an unverified one and stop the demo exercising what ships."""
    assert "en" not in browser_bridge.BRIDGED_LOCALES
    assert browser_bridge.recogniser_for(DEV_ON, "en") is None


@pytest.mark.parametrize("locale", ["ta", "te", "mr", "pa", "gu", "bn"])
def test_an_unbridged_locale_gets_nothing(locale: str) -> None:
    """The bridge covers CC-010's gap and not a language wave. §2.4 admits a
    locale through the §12 gate, and a browser recogniser is not that gate."""
    assert browser_bridge.recogniser_for(DEV_ON, locale) is None


def test_the_bridge_never_routes_hindi_to_an_english_recogniser() -> None:
    """The failure CC-010 exists to prevent, asserted directly: every bridged
    locale asks for an INDIC tag, never `en-*`."""
    for locale in browser_bridge.BRIDGED_LOCALES:
        lang = browser_bridge.RECOGNISER_LANG[locale]
        assert lang.startswith("hi-"), lang


# ---------------------------------------------------------------------------
# 4. The known-wrong bit is written down rather than discovered
# ---------------------------------------------------------------------------


def test_the_script_caveat_is_stated_in_the_module() -> None:
    """hi-Latn transcripts come back in Devanagari, which contradicts §2.4's
    "hi-Latn IS Latin script". That is a real defect of the bridge, and the
    honest place for it is the module that causes it."""
    assert "DEVANAGARI" in browser_bridge.SCRIPT_CAVEAT
    assert "hi-Latn" in browser_bridge.SCRIPT_CAVEAT
