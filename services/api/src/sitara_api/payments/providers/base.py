"""The one payment-provider interface (§30.3, §6.3, §13).

This file is `voice/providers/base.py` and `panchang/providers/base.py` applied
to money, and it keeps their two rules for their two reasons:

1. **Adapters return NORMALISED types, never vendor JSON.** Razorpay calls a
   failed mandate one thing and Stripe calls it another; §30.3 requires "mapped
   reasons in plain language", and the mapping happens HERE so that no vendor's
   vocabulary ever reaches a screen, a log or a database row.
2. **Adapters raise `PaymentProviderUnavailable`, never an upstream body.**
   §34.4 has `PAY_PROVIDER_ERROR` for exactly this, and §13 keeps vendor
   payloads out of logs — an exception that travels tends to end up in both.

A third rule belongs to money alone, and it is the one that would actually cost
something:

3. **No method here returns or accepts an instrument.** There is no card
   number, no VPA, no token in any signature in this file. §30.3 puts the
   collection on the rail's own hosted surface ("Razorpay/Stripe hosted
   surfaces — we never touch PANs") and §13 scopes us to PCI SAQ-A. That is a
   property of the INTERFACE rather than of anyone's discipline: an adapter
   cannot hand us a PAN through a shape that has nowhere to put one, and the
   `checkout_url` that `PurchaseIntent` carries instead is the whole mechanism
   — we send the user to the rail and the rail tells us what happened.

── What the simulator is, and what it is not ───────────────────────────────

`SimulatedRail` is the only implementation this milestone ships and it is a
first-class one: it implements this interface exactly, it is selected through
the same `routing.resolve()` every real rail will be, and every state §30.3
names is reachable through it. It is not a test double — `tests/payments` runs
against it because it is the shipped arm, not because it is convenient.

What it is not is a rail. It moves no money, and `routing.CAPABILITIES` says so
in the one place that decides what may serve a region — so a deployment that
believed it had payments would be a deployment that had read the matrix and
seen `simulator`.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from sitara_schemas.payments import BillingRegion, PaymentFailureReason, PlanId

from sitara_api.payments.money import Money


class PaymentProviderName(StrEnum):
    """The rails, as far as this milestone implements them.

    `RAZORPAY` and `STRIPE` are members even though neither has a working
    adapter, and that is deliberate — the opposite of `VoiceProviderName`,
    which excludes ElevenLabs and Azure precisely because naming a provider
    with no implementation lets configuration choose one and fail at runtime.

    The difference is `routing.CAPABILITIES`. Voice had no matrix when that
    enum was written; this one does, so a name here cannot be selected unless
    its cell says IMPLEMENTED, and naming the two rails §30.3 actually
    specifies is what makes the gap VISIBLE — in the matrix, in `/shipcheck`,
    and in `PAY_RAIL_UNAVAILABLE` — rather than absent.
    """

    #: §30.3's India rail. DECLARED — no adapter, no account, no keys.
    RAZORPAY = "razorpay"
    #: §30.3's international rail. DECLARED — same.
    STRIPE = "stripe"
    #: The prototype's rail. IMPLEMENTED, and moves no money.
    SIMULATOR = "simulator"


class PaymentProviderUnavailable(RuntimeError):
    """The rail could not answer. Maps to §34.4's `PAY_PROVIDER_ERROR`.

    Deliberately not carrying the upstream body — see the module header. A
    provider's error string is vendor English in a §2.4 product and a payload
    §13 keeps out of logs, and it is both at once here.
    """


class PaymentProviderNotImplemented(PaymentProviderUnavailable):
    """This rail is DECLARED and has no adapter behind it.

    A subclass rather than a separate exception so that every caller's existing
    `except PaymentProviderUnavailable` already handles it — a rail that is not
    built and a rail that is down are the same thing to a purchase flow, and
    they are different things to `/shipcheck`, which is where the distinction
    is read.
    """


class EventKind(StrEnum):
    """What a rail tells us happened. The NORMALISED set.

    Every rail's webhook taxonomy collapses into these five. They are the
    events that change state on our side; a rail emitting anything else is
    emitting something we do not act on, and an adapter maps it to nothing
    rather than inventing a member for it.
    """

    PAYMENT_SUCCEEDED = "payment.succeeded"
    PAYMENT_FAILED = "payment.failed"
    #: §30.3 — the UPI mandate came back rejected AFTER a successful charge.
    #: Not a payment failure: the money arrived and the standing instruction
    #: for the next one did not, and confusing the two cancels a subscription
    #: somebody has already paid for.
    MANDATE_REJECTED = "mandate.rejected"
    REFUND_SUCCEEDED = "refund.succeeded"
    #: A scheduled renewal the rail attempted and could not collect. Distinct
    #: from PAYMENT_FAILED, which is a purchase the user was watching happen.
    RENEWAL_FAILED = "renewal.failed"


@dataclass(frozen=True)
class PurchaseRequest:
    """What we ask a rail to collect.

    No instrument, by construction — see rule 3 in the module header. The
    `idempotency_key` is §30.3's own word and §6.3's requirement on every
    mutation endpoint; it is OURS, generated before the rail is called, so that
    a request that times out on the way there can be retried without the risk
    of a second charge.
    """

    user_id: str
    plan: PlanId
    region: BillingRegion
    amount: Money
    idempotency_key: str
    locale: str = "en"


@dataclass(frozen=True)
class PurchaseIntent:
    """The rail's answer to `open_purchase`.

    `checkout_url` is where the user goes to enter an instrument we never see.
    `pending` is §30.3's UPI hold: the rail has the mandate and is waiting for
    the user's approval, which is neither success nor failure and gets its own
    5-minute screen.
    """

    provider: PaymentProviderName
    provider_ref: str
    checkout_url: str | None
    pending: bool
    #: Set only when the rail declined immediately. Always a MAPPED reason —
    #: a vendor code here would reach a screen in the wrong language.
    failure_reason: PaymentFailureReason | None = None


@dataclass(frozen=True)
class ProviderEvent:
    """One normalised webhook.

    `provider_event_id` is the rail's own id for the event and is what §6.4's
    unique index on `payments.provider_event_id` is built over — so the
    duplicate guard is the database's, not a remembered `if`.

    `idempotency_key` is OURS and answers a different question. The event id
    catches a REDELIVERY of one event; the idempotency key catches two
    genuinely distinct events that both charged for one purchase, which §30.3
    handles by refunding rather than by ignoring. Two ids, two failure modes,
    and collapsing them into one field would silently pick which of the two to
    stop guarding against.
    """

    provider_event_id: str
    kind: EventKind
    #: The rail's reference for the THING the event is about — the purchase,
    #: the subscription, the mandate. This is the JOIN between a webhook and an
    #: account: `start_purchase` stores it on the row and the event carries it
    #: back, so nothing about the user ever travels to the rail (§13).
    #:
    #: It is a FIELD rather than something recoverable from the event id,
    #: because one reference legitimately produces many events — a charge, its
    #: duplicate, a refund — and an id that encoded the reference would make
    #: "which purchase is this about" a string-slicing exercise that happens to
    #: work for one rail's id format.
    provider_ref: str
    idempotency_key: str | None
    amount: Money | None
    occurred_at: dt.datetime
    failure_reason: PaymentFailureReason | None = None
    #: §6.4's `payments.instrument_ref` — a rail-side TOKEN, never an
    #: instrument. CSFLE-encrypted under the `payment` key class at rest.
    instrument_ref: str | None = None
    #: §22.1 — the rail's own invoice id, for a GST invoice that must stay
    #: attached to its original transaction entity (§30.3's migration policy).
    invoice_ref: str | None = None


@dataclass(frozen=True)
class RefundRequest:
    provider_ref: str
    amount: Money
    idempotency_key: str


class PaymentProvider(Protocol):
    """Every rail implements exactly this.

    Five methods, and each is one thing §30.3 needs a rail to do. Notably
    ABSENT: anything that reads a subscription's state back from the rail. The
    subscription lives in `subscriptions` and its lifecycle is §22.13's, which
    is ours — a rail that owned it would make "what does this user have" a
    question with two answers, and §14's reconciliation target exists precisely
    because the two would eventually disagree.
    """

    name: PaymentProviderName

    async def open_purchase(self, request: PurchaseRequest) -> PurchaseIntent:
        """Begin a collection. Returns where to send the user."""
        ...

    async def charge_renewal(
        self, request: PurchaseRequest, *, provider_ref: str
    ) -> PurchaseIntent:
        """Collect against a stored mandate or token. §22.13's renewal."""
        ...

    async def refund(self, request: RefundRequest) -> ProviderEvent:
        """§22.16's 7-day window and §30.3's automatic duplicate reversal."""
        ...

    async def cancel_mandate(self, *, provider_ref: str) -> None:
        """Stop the standing instruction. §30.3's cancellation, rail-side.

        Returns nothing: the SUBSCRIPTION's cancellation is our state change
        and happens whether or not the rail acknowledges, because §30.3
        promises "immediate confirm" and a user must never be held in a
        cancellation flow by a vendor's availability.
        """
        ...

    def verify_webhook(self, *, payload: bytes, signature: str) -> ProviderEvent:
        """Authenticate and normalise one delivery.

        §13 requires "webhook signature verification both payment rails", and
        it is on this interface rather than beside it because an unverified
        webhook is an unauthenticated instruction to grant paid access. A rail
        that cannot verify must raise, never return.
        """
        ...
