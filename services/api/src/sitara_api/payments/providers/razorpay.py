"""Razorpay — DECLARED, not implemented (§30.3, §22.13, §22.1).

This file is a placeholder in the strict sense: it holds the place, so that the
shape of the gap is visible and the work of closing it is a known quantity
rather than a discovery.

**Every method raises.** Not "returns a stub", not "logs a warning and
succeeds" — raises `PaymentProviderNotImplemented`, which is a
`PaymentProviderUnavailable`, which every caller already handles as §34.4's
`PAY_PROVIDER_ERROR`. And it is unreachable anyway: `routing.CAPABILITIES` has
this rail DECLARED, `resolve()` never selects a DECLARED cell, and
`tests/payments/test_routing.py` asserts that it cannot be.

Two guards, deliberately, because they fail differently. The matrix is what
keeps the rail out of the product; the raise is what keeps a future caller that
constructs this class directly — bypassing `resolve()`, which is exactly how a
"quick test against the real thing" gets written — from silently doing nothing
and reporting success.

── What closing this gate actually requires ────────────────────────────────

Recorded here so it is a list rather than an unknown. None of it is code:

  1. A Razorpay account with KYC completed for the Indian entity (§22.1 puts
     both rails' KYC in W2 procurement, with legal counsel + finance owning
     it), plus GST registration and the LUT filing.
  2. API keys, and a webhook secret, in AWS Secrets Manager per §13 — never in
     an env file.
  3. A Razorpay Subscriptions plan per (region, plan) cell of
     `money.PRICES`, created against the same prices, because a price that
     lives in two systems is a price that will differ in one of them.
  4. The UPI Autopay per-transaction cap verified against prevailing RBI
     limits (§22.13 says this is a W2 check and states the fallback: "if a cap
     intervenes, annual defaults to card/netbanking with UPI for monthly").

The CODE is the smaller half: implement the five `PaymentProvider` methods,
map Razorpay's failure codes onto `PaymentFailureReason`, verify the webhook
signature with their scheme, and flip one cell of `routing.CAPABILITIES` from
DECLARED to IMPLEMENTED. `payments/service.py` does not change, because it has
never known which rail answered.
"""

from __future__ import annotations

from sitara_api.payments.providers.base import (
    PaymentProviderName,
    PaymentProviderNotImplemented,
    ProviderEvent,
    PurchaseIntent,
    PurchaseRequest,
    RefundRequest,
)

_REASON = (
    "Razorpay is DECLARED in `payments.providers.routing.CAPABILITIES` and has no "
    "adapter behind it. It needs an account, KYC, keys and a plan catalogue before "
    "it can be written — see this module's header and the `payments.live_rails` "
    "release gate. Nothing selects it: `resolve()` never returns a DECLARED cell."
)


class RazorpayRail:
    """§30.3's India rail. Every method raises — see the module header."""

    name = PaymentProviderName.RAZORPAY

    async def open_purchase(self, request: PurchaseRequest) -> PurchaseIntent:
        raise PaymentProviderNotImplemented(_REASON)

    async def charge_renewal(
        self, request: PurchaseRequest, *, provider_ref: str
    ) -> PurchaseIntent:
        raise PaymentProviderNotImplemented(_REASON)

    async def refund(self, request: RefundRequest) -> ProviderEvent:
        raise PaymentProviderNotImplemented(_REASON)

    async def cancel_mandate(self, *, provider_ref: str) -> None:
        raise PaymentProviderNotImplemented(_REASON)

    def verify_webhook(self, *, payload: bytes, signature: str) -> ProviderEvent:
        # The one method where "not implemented" and "returns nothing useful"
        # must not be confused: a verifier that returned anything rather than
        # raising would be a verifier that accepted an unsigned delivery.
        raise PaymentProviderNotImplemented(_REASON)
