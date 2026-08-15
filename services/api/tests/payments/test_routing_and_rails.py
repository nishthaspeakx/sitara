"""The adapter's honesty (§30.3, §3.2's adapter discipline).

`tests/voice/test_routing.py` guards CC-010's ruling by asserting the SHAPE of
the routing module rather than only its current answers. This does the same for
money, and the stakes are the mirror image: voice's silent fallback produces
fluent nonsense, and a payment rail's silent fallback charges the wrong entity
in the wrong currency under the wrong tax treatment (§22.1).

The tests that matter most here are the ones about what CANNOT happen:

  · a DECLARED rail is never selected, however it is reached
  · `resolve` has no fallback parameter and no default argument
  · landing a real rail is ONE cell, asserted literally
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from sitara_schemas.payments import BillingRegion

from sitara_api.payments.providers import routing
from sitara_api.payments.providers.base import (
    PaymentProviderName,
    PaymentProviderNotImplemented,
    PaymentProviderUnavailable,
)
from sitara_api.payments.providers.razorpay import RazorpayRail
from sitara_api.payments.providers.simulator import SimulatedRail
from sitara_api.payments.providers.stripe import StripeRail


def test_both_real_rails_are_declared_and_neither_is_selected() -> None:
    """The state of the world, stated once so it cannot be misread.

    If this test starts failing because a cell went IMPLEMENTED, that is the
    milestone landing — update it deliberately, in the same commit as the
    adapter.
    """
    assert routing.unimplemented_rails() == (
        (PaymentProviderName.RAZORPAY, BillingRegion.INDIA),
        (PaymentProviderName.STRIPE, BillingRegion.INTERNATIONAL),
    )
    for region in BillingRegion:
        assert routing.resolve(region).provider is PaymentProviderName.SIMULATOR


def test_resolve_has_no_fallback_parameter_and_no_default() -> None:
    """The signature IS the guarantee.

    `voice.providers.routing` carries the same test for CC-010, and for the
    same reason: the way a no-silent-fallback ruling gets reversed is somebody
    adding a sensible-looking default to a function that had none. Asserting
    the signature catches that in review rather than in production.
    """
    signature = inspect.signature(routing.resolve)
    assert list(signature.parameters) == ["region"]
    assert signature.parameters["region"].default is inspect.Parameter.empty


def test_the_routing_module_contains_no_fallback_to_the_simulator() -> None:
    """No `or SIMULATOR` anywhere, checked in the source.

    A prototype's most likely regression is exactly this line, written kindly:
    "if no real rail, use the simulator". It would make a production
    deployment silently issue receipts for money nobody collected. The
    simulator is reachable only as a CELL, and only because its cell says
    IMPLEMENTED.
    """
    source = Path(inspect.getfile(routing)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
            for value in node.values:
                assert not (
                    isinstance(value, ast.Attribute) and value.attr == "SIMULATOR"
                ), "a fallback to the simulator would issue receipts for money nobody took"


def test_landing_razorpay_is_ONE_cell() -> None:
    """§3.2's promise, asserted literally rather than described.

    Flip one cell; the rail is selected; nothing else changes. The matrix is
    restored in a `finally` — a leaked mutation would make every other test in
    this file pass for the wrong reason, which is the failure mode
    `test_landing_sarvam_streaming_is_ONE_cell` was written to avoid.
    """
    cell = (PaymentProviderName.RAZORPAY, BillingRegion.INDIA)
    before = routing.CAPABILITIES[cell]
    try:
        routing.CAPABILITIES[cell] = routing.Support.IMPLEMENTED
        assert routing.resolve(BillingRegion.INDIA).provider is PaymentProviderName.RAZORPAY
        # And the OTHER region is untouched by it.
        assert (
            routing.resolve(BillingRegion.INTERNATIONAL).provider
            is PaymentProviderName.SIMULATOR
        )
    finally:
        routing.CAPABILITIES[cell] = before
    assert routing.CAPABILITIES[cell] is routing.Support.DECLARED


def test_a_region_with_no_rail_at_all_resolves_to_nobody() -> None:
    """`provider=None` is a designed state, not an error.

    Forced by removing every cell for one region — which is the state a real
    deployment is in today for both, if the simulator is not permitted there.
    """
    saved = {
        key: value
        for key, value in routing.CAPABILITIES.items()
        if key[1] is BillingRegion.INDIA
    }
    try:
        for key in saved:
            routing.CAPABILITIES[key] = routing.Support.UNSUPPORTED
        route = routing.resolve(BillingRegion.INDIA)
        assert route.provider is None
        assert route.available is False
        # §2.4 — a message KEY, never a sentence. This reason reaches a screen.
        assert route.reason_key == "errors.pay.rail_unavailable"
        assert routing.purchases_available_in(BillingRegion.INDIA) is False
    finally:
        routing.CAPABILITIES.update(saved)


def test_a_declared_rail_reports_pending_rather_than_unavailable() -> None:
    """DECLARED and UNSUPPORTED are different answers and get different keys.

    "Nobody has built this yet" and "this vendor does not do that" are the same
    outcome for the user and completely different facts for the team — and the
    release gate reads the first one. Collapsing them is how a real blocker
    stops being visible.
    """
    cell = (PaymentProviderName.SIMULATOR, BillingRegion.INDIA)
    before = routing.CAPABILITIES[cell]
    try:
        routing.CAPABILITIES[cell] = routing.Support.UNSUPPORTED
        route = routing.resolve(BillingRegion.INDIA)
        assert route.provider is None
        assert route.support is routing.Support.DECLARED
        assert route.reason_key == "errors.pay.rail_pending"
    finally:
        routing.CAPABILITIES[cell] = before


@pytest.mark.parametrize("rail", [RazorpayRail(), StripeRail()])
@pytest.mark.asyncio
async def test_an_unimplemented_rail_raises_rather_than_quietly_succeeding(rail) -> None:  # noqa: ANN001
    """The second guard.

    The matrix keeps these rails out of the product. This keeps a future caller
    that constructs one directly — which is exactly how a "quick test against
    the real thing" gets written — from silently doing nothing and reporting
    success. `PaymentProviderNotImplemented` is a `PaymentProviderUnavailable`,
    so every existing handler already covers it.
    """
    with pytest.raises(PaymentProviderNotImplemented):
        await rail.cancel_mandate(provider_ref="anything")
    with pytest.raises(PaymentProviderUnavailable):
        rail.verify_webhook(payload=b"{}", signature="whatever")


def test_the_simulator_verifies_a_real_signature() -> None:
    """§13's one security property on the webhook path, exercised for real.

    A simulator that accepted any delivery would leave the code that grants
    paid access on a webhook having never once run behind a signature check.
    """
    rail = SimulatedRail()
    payload, signature = rail.sign(
        {
            "provider_event_id": "sim_evt_1",
            "provider_ref": "sim_pi_000001",
            "kind": "payment.succeeded",
            "idempotency_key": "k",
            "amount": {"minor": 49900, "currency": "INR"},
            "occurred_at": "2026-08-15T09:00:00+00:00",
        }
    )
    event = rail.verify_webhook(payload=payload, signature=signature)
    assert event.provider_event_id == "sim_evt_1"

    with pytest.raises(PaymentProviderUnavailable):
        rail.verify_webhook(payload=payload, signature="0" * 64)
    # A tampered BODY under the original signature — the case a naive
    # implementation that hashed only an id would miss entirely.
    with pytest.raises(PaymentProviderUnavailable):
        rail.verify_webhook(payload=payload.replace(b"49900", b"99900"), signature=signature)


def test_the_interface_has_nowhere_to_put_an_instrument() -> None:
    """§13 / PCI SAQ-A, as a property of the shape rather than of discipline.

    §30.3 keeps collection on the rail's hosted surface — "we never touch
    PANs". An adapter cannot hand us one through a type with no field for it,
    and this asserts that no such field has been added by anybody's convenience.
    """
    from sitara_api.payments.providers import base

    forbidden = ("card", "pan", "cvv", "vpa", "upi_id", "account_number", "iban")
    for name in ("PurchaseRequest", "PurchaseIntent", "ProviderEvent", "RefundRequest"):
        fields = set(getattr(base, name).__dataclass_fields__)
        assert not (fields & set(forbidden)), f"{name} grew an instrument field"
        # `instrument_ref` is permitted and is a rail-side TOKEN — §6.4 marks
        # it encrypted under the `payment` key class for exactly that reason.
        assert "instrument" not in fields


def test_the_release_gate_reads_the_matrix_and_the_dev_surface_cannot_move_it() -> None:
    """A gate whose status a demo flag could change is not a gate.

    `test_prototype.py` asserts the same thing about §33.5 by reading the
    source of `release_gates` and `call_gate`. The payments gate has the same
    exposure and a worse consequence: it is the one that says "no money can be
    collected yet", and a control surface that could close it would let a
    prototype report itself ready to take payments.
    """
    from sitara_api import release_gates

    source = Path(inspect.getfile(release_gates)).read_text(encoding="utf-8")
    assert "dev_router" not in source
    assert "prototype" not in source

    gate = next(g for g in release_gates.gates() if g.id == "payments.live_rails")
    assert gate.open is True
    assert "razorpay/india" in gate.status
    assert "stripe/international" in gate.status

    # And it closes ITSELF when the matrix changes — not when someone edits a
    # string here.
    cells = [
        (PaymentProviderName.RAZORPAY, BillingRegion.INDIA),
        (PaymentProviderName.STRIPE, BillingRegion.INTERNATIONAL),
    ]
    before = {cell: routing.CAPABILITIES[cell] for cell in cells}
    try:
        for cell in cells:
            routing.CAPABILITIES[cell] = routing.Support.IMPLEMENTED
        closed = next(g for g in release_gates.gates() if g.id == "payments.live_rails")
        assert closed.open is False
    finally:
        routing.CAPABILITIES.update(before)


def test_the_registry_covers_every_rail_in_the_enum() -> None:
    """A rail named in the enum with no class would fail at the first purchase
    rather than at boot. This is the boot-time half."""
    from sitara_api.payments.providers.registry import _RAILS

    assert set(_RAILS) == set(PaymentProviderName)
