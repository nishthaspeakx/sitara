"""Stripe — DECLARED, not implemented (§30.3, §22.1).

`razorpay.py`'s header explains the shape and the two guards; this is the same
file for the international rail and the difference is only in what closing it
requires.

**Every method raises**, and `routing.CAPABILITIES` has this rail DECLARED so
`resolve()` never selects it.

── What closing this gate actually requires ────────────────────────────────

  1. A **Stripe India** account for the Indian entity — §22.1 is specific that
     this is not a US Stripe account: the diaspora is billed as a "zero-rated
     export of services under LUT", with foreign-currency receipts arriving
     through Stripe's export settlement. A US-entity Stripe account would be a
     different tax posture and would need the Delaware flip §22.1 defers.
  2. Keys and a webhook signing secret in AWS Secrets Manager (§13).
  3. Products and Prices matching `money.PRICES` for the international cells,
     including §10-20's $79 founding annual.
  4. SCA/3DS handling — §30.3 says "Stripe; SCA-ready", which means the
     purchase flow must treat a `requires_action` intent as a real state and
     not as a failure. It maps onto `PurchaseIntent.pending`, which already
     exists for §30.3's UPI hold; the two are different causes of the same
     screen and neither is an error.
  5. Smart Retries configured, because §22.13 names it as the Stripe-side
     dunning mechanism — note that it retries on Stripe's schedule while
     §22.13's grace clock runs on ours. The two must not both decide when
     access ends: ours does, and a Smart Retry that succeeds inside the grace
     arrives here as an ordinary renewal event.

The CODE is again the smaller half: five methods, a failure-code mapping onto
`PaymentFailureReason`, `Stripe-Signature` verification, and one cell flipped
from DECLARED to IMPLEMENTED.
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
    "Stripe is DECLARED in `payments.providers.routing.CAPABILITIES` and has no "
    "adapter behind it. It needs a Stripe INDIA account (§22.1 — zero-rated export "
    "under LUT, not a US entity), keys, a price catalogue and SCA handling before it "
    "can be written — see this module's header and the `payments.live_rails` release "
    "gate. Nothing selects it: `resolve()` never returns a DECLARED cell."
)


class StripeRail:
    """§30.3's international rail. Every method raises — see the header."""

    name = PaymentProviderName.STRIPE

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
        raise PaymentProviderNotImplemented(_REASON)
