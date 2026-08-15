"""PROTOTYPE MODE's four conditions, each asserted.

It is a demo aid that lifts §33.5's release gate and §7.3's entitlement
ceiling, so the tests that matter are the ones proving it cannot reach
anything it should not — and, above all, that **it cannot move a gate's
reported status**. A gate a demo flag can influence is not a gate.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from sitara_api import prototype
from sitara_api.config import Settings

DEV = {"environment": "dev"}


# ---------------------------------------------------------------------------
# 1. it refuses to activate outside dev, loudly
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("environment", ["test", "staging", "production", "prod", ""])
def test_it_refuses_to_activate_outside_dev(environment: str) -> None:
    settings = Settings(prototype_mode=True, environment=environment)
    with pytest.raises(prototype.PrototypeModeRefused, match="runs only in 'dev'"):
        prototype.assert_safe(settings)


@pytest.mark.parametrize("environment", ["test", "staging", "production"])
def test_the_app_refuses_to_BOOT_with_it_set_outside_dev(environment: str) -> None:
    """Not a log line and not a degraded mode.

    A demo aid that silently did nothing in staging is worse than one that
    crashes: nobody notices it is set, and the next person to read the config
    believes it does something.
    """
    from sitara_api.app import create_app

    with pytest.raises(prototype.PrototypeModeRefused):
        create_app(Settings(prototype_mode=True, environment=environment))


@pytest.mark.parametrize("environment", ["test", "staging", "production", ""])
def test_every_resolver_stays_false_outside_dev(environment: str) -> None:
    """`is_active` re-checks the environment on EVERY read rather than trusting
    that `assert_safe` ran. A resolver that leaned on a boot-time check would be
    one import away from being reached by something that never booted."""
    settings = Settings(prototype_mode=True, environment=environment)
    assert prototype.is_active(settings) is False
    assert prototype.calls_enabled(settings) is False
    assert prototype.stories_enabled(settings) is False
    assert prototype.lifts_entitlement_ceiling(settings) is False


def test_it_does_activate_in_dev() -> None:
    """The converse, so this file fails if the switch silently stops working
    rather than only if it works too widely."""
    settings = Settings(prototype_mode=True, **DEV)
    prototype.assert_safe(settings)
    assert prototype.is_active(settings) is True
    assert prototype.calls_enabled(settings) is True
    assert prototype.stories_enabled(settings) is True
    assert prototype.lifts_entitlement_ceiling(settings) is True


# ---------------------------------------------------------------------------
# 2. shipped defaults are exactly as they were
# ---------------------------------------------------------------------------


def test_shipped_defaults_are_untouched() -> None:
    """Nothing here writes to `Settings`. A deployment that never sets the
    switch behaves precisely as it did before this file existed."""
    # The DECLARED defaults, not `Settings()` — which loads the ambient
    # `services/api/.env` and so asserted whatever the developer had set. It
    # passed until someone enabled prototype mode for a local walkthrough, which
    # is precisely what the switch is for.
    for field in ("prototype_mode", "calls_enabled", "stories_enabled"):
        assert Settings.model_fields[field].default is False, field
    settings = Settings(_env_file=None)
    # …and with the switch off, the resolvers are the settings themselves.
    assert prototype.calls_enabled(settings) is settings.calls_enabled
    assert prototype.stories_enabled(settings) is settings.stories_enabled


def test_the_resolvers_only_ever_WIDEN() -> None:
    """`setting OR prototype`, never `prototype AND setting`. The switch can
    turn something on; it can never turn something off — which is what keeps it
    from being usable as a way to disable a guard."""
    on = Settings(calls_enabled=True, stories_enabled=True, environment="production")
    assert prototype.calls_enabled(on) is True
    assert prototype.stories_enabled(on) is True


# ---------------------------------------------------------------------------
# 3. release-gate statuses are NEVER influenced — the condition that matters
# ---------------------------------------------------------------------------


def test_release_gate_statuses_are_identical_with_and_without_prototype() -> None:
    from sitara_api import release_gates

    def snapshot() -> list[tuple[str, str, bool]]:
        return [(g.id, g.status, g.open) for g in release_gates.gates()]

    before = snapshot()
    prototype.assert_safe(Settings(prototype_mode=True, **DEV))
    assert snapshot() == before


def test_the_33_5_call_gate_reads_the_same_and_still_does_not_pass() -> None:
    """§33.5 is the gate prototype mode is most tempting to move, because
    moving it is what would make calls 'shippable'. It must read identically."""
    from sitara_api.voice import call_gate

    before = call_gate.evaluate()
    prototype.assert_safe(Settings(prototype_mode=True, **DEV))
    after = call_gate.evaluate()

    assert after.results == before.results
    assert after.values == before.values
    assert after.passes is False
    assert call_gate.render(after) == call_gate.render(before)


def test_the_gates_cannot_even_SEE_prototype_mode() -> None:
    """The structural half, and the one that survives a refactor.

    Equality of two evaluations proves today's behaviour; this proves the gates
    have no way to depend on the switch at all. If someone later imports it
    into either module — for a 'harmless' demo affordance — this fails, and it
    fails in the file that explains why that is not harmless.
    """
    from sitara_api import release_gates
    from sitara_api.voice import call_gate

    for module in (release_gates, call_gate):
        source = Path(inspect.getfile(module)).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        assert not any("prototype" in name for name in imported), (
            f"{module.__name__} imports the prototype module. A gate whose "
            "status a demo flag can reach is not a gate."
        )
        assert "prototype" not in source, (
            f"{module.__name__} mentions prototype mode in its source."
        )


def test_cc_010_is_not_unblocked_by_prototype_mode() -> None:
    """The one thing a demo must never 'unblock'.

    `hi`/`hi-Latn` have no streaming recogniser, so lifting the locale ruling
    would route Hindi audio to an English model — which does not fail, it
    produces fluent nonsense that reaches §9 as the user's question. A demo of
    that is worse than no demo.
    """
    from sitara_api.voice.providers.routing import Modality, resolve

    prototype.assert_safe(Settings(prototype_mode=True, **DEV))
    for locale in ("hi", "hi-Latn"):
        assert resolve(Modality.STREAMING, locale).available is False


# ---------------------------------------------------------------------------
# 4. the entitlement ceiling, lifted — and only the ceiling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_minute_pool_is_unlimited_in_prototype_mode() -> None:
    import datetime as dt

    from sitara_api.voice.entitlements import MinuteLedger

    ledger = MinuteLedger(db=None, settings=Settings(prototype_mode=True, **DEV))
    entitlement = await ledger.load("6a70000000000000000000a1", now=dt.datetime.now(dt.UTC))

    assert entitlement.unlimited is True
    assert entitlement.exhausted is False


@pytest.mark.asyncio
async def test_without_the_switch_the_ledger_meters_exactly_as_before() -> None:
    """`settings` is optional and defaults to None, so every existing caller —
    and every test written before this file — gets the metering it had."""
    import datetime as dt

    from sitara_api.voice.entitlements import CallPlan, MinuteLedger

    ledger = MinuteLedger(db=None)  # no settings at all
    entitlement = await ledger.load("6a70000000000000000000a1", now=dt.datetime.now(dt.UTC))
    # No db → the fail-toward-the-smallest-pool path, unchanged.
    assert entitlement.plan is CallPlan.NONE
