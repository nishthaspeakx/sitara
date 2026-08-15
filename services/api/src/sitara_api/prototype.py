"""PROTOTYPE MODE — one switch that unblocks a local demo (dev only).

**This is a demo aid. It is not a configuration option and it is not a way to
ship anything.** Its whole job is to let the founder walk through the product
end to end on a laptop without a human-review gate stopping the tour.

Why it exists as ONE switch
----------------------------

The alternative is a scatter of env vars — `CALLS_ENABLED`, `STORIES_ENABLED`,
some entitlement override — each of which is individually plausible in a
deployed environment and therefore individually dangerous. One switch, named
for exactly what it is, is easier to grep for, easier to refuse, and impossible
to set "just the harmless part of" by accident.

The four conditions, and how each is enforced
----------------------------------------------

1. **It refuses to activate outside dev, loudly.** `assert_safe` raises at app
   boot if the switch is set in any other environment. Not ignored, not logged
   and continued — the same refusal `db.seed`, the local CSFLE KMS and
   `DevPhoneVerifier` all make, because a demo aid that can reach real data is
   not a demo aid.

2. **Shipped defaults are untouched.** Nothing here writes to `Settings`.
   `calls_enabled` is still `False`, `stories_enabled` is still `False`, and a
   deployment that never sets the switch behaves exactly as it did before this
   file existed. The resolvers below are `setting OR prototype`, so the switch
   can only ever widen, never narrow, and only ever in dev.

3. **Release-gate statuses are never influenced.** `release_gates.py` and
   `voice/call_gate.py` do not import this module, and
   `tests/test_prototype.py` asserts that by reading their source. A gate whose
   status could be moved by a demo flag is not a gate — it is a light switch
   next to a fire alarm. **The §33.5 table reads the same in prototype mode as
   out of it, and `passes` stays False.**

4. **It is documented as a demo aid**, in the runbook, beside the live-call
   procedure — not in a settings reference where it would read as an option.

What it unblocks, and what it deliberately does not
----------------------------------------------------

Unblocked: `calls_enabled` (§33.5's conditional release), `stories_enabled`
(§30.6's P1 experiment), and §7.3's minute ceiling (an unlimited pool, so a
demo cannot end mid-sentence on a quota).

NOT unblocked, and each for its own reason:

- **CC-010's locale ruling.** `hi`/`hi-Latn` calls stay refused. There is no
  Hindi streaming recogniser, so "unblocking" it would route Hindi audio to an
  English model — which does not fail, it produces fluent nonsense that reaches
  §9 as the user's question. A demo of that is worse than no demo.
- **§9's safety ladder, every validator, and cite-or-die.** None of it is a
  gate awaiting a human; it is the product working. A prototype that turned it
  off would be demonstrating something Sitara is not.
- **`step_up_enforced`.** Enabling it would block more, not less.
- **CSFLE.** Encryption is not a review gate.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

#: The one environment prototype mode may run in. Not a list, not configurable.
REQUIRED_ENVIRONMENT = "dev"


class PrototypeModeRefused(RuntimeError):
    """Raised at boot when the switch is set outside dev."""


def assert_safe(settings: Any) -> None:
    """Called once, at app construction. Raises rather than degrading.

    A demo aid that silently did nothing in staging would be worse than one
    that crashes: nobody would notice it was set, and the next person to read
    the config would believe it was doing something.
    """
    if not getattr(settings, "prototype_mode", False):
        return
    environment = getattr(settings, "environment", "")
    if environment != REQUIRED_ENVIRONMENT:
        raise PrototypeModeRefused(
            f"SITARA_PROTOTYPE is set but environment is {environment!r}. "
            f"Prototype mode runs only in {REQUIRED_ENVIRONMENT!r} — it lifts "
            "§33.5's release gate and §7.3's entitlement ceiling, and there is "
            "no safe non-dev use of either."
        )
    logger.warning(
        "PROTOTYPE MODE is ON (dev only). Calls and Stories are forced on and "
        "the §7.3 minute pool is unlimited. Release-gate statuses are UNAFFECTED "
        "and still report the truth — run `python -m sitara_api.release_gates`."
    )


def is_active(settings: Any) -> bool:
    """True only when the switch is set AND the environment is dev.

    Both halves, every time. `assert_safe` has already refused the unsafe
    combination at boot, but this does not lean on that having been called —
    a resolver that trusted a boot-time check would be one import away from
    being reached by something that never booted the app.
    """
    return (
        bool(getattr(settings, "prototype_mode", False))
        and getattr(settings, "environment", "") == REQUIRED_ENVIRONMENT
    )


# ---------------------------------------------------------------------------
# Resolvers. Each is `setting OR prototype` — widening only, never narrowing.
# ---------------------------------------------------------------------------


def calls_enabled(settings: Any) -> bool:
    """§33.5's flag, as the CALL DOOR should read it.

    The gate itself is untouched and still does not pass; this only decides
    whether a local demo may open a call. `calls/router.py` asks this instead
    of reading `settings.calls_enabled` directly.
    """
    return bool(getattr(settings, "calls_enabled", False)) or is_active(settings)


def stories_enabled(settings: Any) -> bool:
    """§30.6's P1 experiment gate, same shape."""
    return bool(getattr(settings, "stories_enabled", False)) or is_active(settings)


def lifts_entitlement_ceiling(settings: Any) -> bool:
    """§7.3's minute pool, unlimited for a demo.

    Read by `MinuteLedger.load`. A demo that ended mid-sentence because a
    seeded account had spent its minutes would be demonstrating the metering
    rather than the product — and §32.9's warnings are separately demonstrable
    by setting a real quota.
    """
    return is_active(settings)


def access_ttl_seconds(settings: Any) -> int:
    """§34.5's access-cookie lifetime, widened for a demo (dev only).

    The shipped default is 900 seconds and is CORRECT — a short access token
    with a long rotating refresh is the whole point of §6.2's cookie posture,
    and `apiCall` already recovers from an expired one with a single-flight
    refresh (the M10 walkthrough's own finding).

    So this does not fix a bug. It removes a demo hazard: a laptop left open
    between the rehearsal and the room crosses fifteen minutes, and the first
    tap of the real demo then spends a round trip on a refresh. That recovery
    is invisible when it works and is one more thing that can be mid-flight
    when someone is watching.

    Widening only, only in dev, and only through `is_active` — a deployment
    that never sets the switch gets 900 exactly as before. The REFRESH ttl is
    deliberately untouched: it is already thirty days, and lengthening the half
    of the pair that rotates would be changing the security posture rather than
    removing a demo hazard.
    """
    declared = int(getattr(settings, "access_ttl_seconds", 900))
    if not is_active(settings):
        return declared
    # Twelve hours: longer than any demo, shorter than the refresh cookie, and
    # obviously a demo number rather than a plausible production one.
    return max(declared, 12 * 3600)
