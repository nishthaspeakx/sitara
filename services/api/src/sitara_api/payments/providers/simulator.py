"""The simulated rail — the only IMPLEMENTED arm (§30.3).

It implements `PaymentProvider` exactly, is selected through the same
`routing.resolve()` a real rail will be, and reaches every state §30.3 names.
It moves no money.

── Everything it does is a FAULT you armed, or the happy path ──────────────

There is no randomness here. Not a seeded RNG, not a "1 in 10 declines" —
nothing. A demo has to be able to show a specific state on demand ("fail the
next renewal"), and a state machine that sometimes does something else is one
whose failures cannot be reproduced by the person who just saw one. `arm()` is
the whole control surface: one fault, consumed by the next operation unless
`sticky`, and the rail is otherwise a rail that always works.

That also makes this the only rail in the codebase whose behaviour is fully
determined by the test that configures it, which is why `tests/payments` needs
no mocking library and no monkeypatching.

── What it deliberately does NOT simulate ──────────────────────────────────

**Signature verification.** `verify_webhook` checks a real HMAC over the real
bytes with a real shared secret. §13 requires "webhook signature verification
both payment rails", and an unverified webhook is an unauthenticated
instruction to grant paid access — the single most valuable thing an attacker
could forge against this service. A simulator that accepted anything would let
the ONE security property of the webhook path go unwritten and unexercised
until the day a real rail arrived, and the code that grants access on a webhook
would ship having never once run behind a signature check. The secret is a
dev-only constant; the verification is the real thing.

**Instruments.** No card number, no VPA, no token that looks like one appears
in this file, because none appears in the interface (§13, PCI SAQ-A). The
`checkout_url` points at the dev control surface, which is where a human
approves or declines — the simulator's stand-in for a hosted rail page, and the
same shape: we send the user away and learn what happened from an event.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import logging
from dataclasses import dataclass, field
from enum import StrEnum

from sitara_schemas.payments import Currency, PaymentFailureReason

from sitara_api.payments.money import Money
from sitara_api.payments.providers.base import (
    EventKind,
    PaymentProviderName,
    PaymentProviderUnavailable,
    ProviderEvent,
    PurchaseIntent,
    PurchaseRequest,
    RefundRequest,
)

logger = logging.getLogger(__name__)

#: Dev-only, and never read from configuration. A simulator whose webhook
#: secret could be set by an env var is a simulator somebody could point at a
#: real deployment's verification path.
SIMULATOR_WEBHOOK_SECRET = b"sitara-simulator-dev-only"


class Fault(StrEnum):
    """What the demo can make the rail do. Each is a state §30.3 names."""

    #: §30.3's UPI 5-minute hold. Not an error.
    HOLD_PENDING = "hold_pending"
    #: An immediate decline, carrying a mapped reason.
    DECLINE = "decline"
    #: §30.3's post-purchase mandate rejection: the charge SUCCEEDS and the
    #: standing instruction does not.
    REJECT_MANDATE = "reject_mandate"
    #: §22.13's renewal that could not be collected.
    FAIL_RENEWAL = "fail_renewal"
    #: The rail itself is down. `PaymentProviderUnavailable`, §34.4's
    #: `PAY_PROVIDER_ERROR` — distinct from a payment that was declined.
    RAIL_DOWN = "rail_down"


@dataclass
class _Armed:
    fault: Fault
    reason: PaymentFailureReason
    #: A sticky fault survives being used. "Fail the next renewal" is one-shot;
    #: "the rail is down" is a condition somebody turns off again.
    sticky: bool


@dataclass
class SimulatedRail:
    """§30.3's rail, minus the money.

    Stateful within one process, which is right for a demo and is why the dev
    control surface and the service share one instance through `app.state`.
    """

    name: PaymentProviderName = PaymentProviderName.SIMULATOR
    _armed: _Armed | None = None
    _seq: int = 0
    #: Every intent it has issued, so `authorisation_event` can mint the event
    #: a real rail would post back and the dev surface can list what is
    #: outstanding. No instrument is stored — there is none to store.
    _intents: dict[str, PurchaseRequest] = field(default_factory=dict)

    # -- control surface ----------------------------------------------------

    def arm(
        self,
        fault: Fault,
        *,
        reason: PaymentFailureReason = PaymentFailureReason.UNKNOWN,
        sticky: bool = False,
    ) -> None:
        """Make the next operation do this. See `Fault`."""
        self._armed = _Armed(fault=fault, reason=reason, sticky=sticky)
        logger.info("simulated rail armed: %s (sticky=%s)", fault.value, sticky)

    def disarm(self) -> None:
        self._armed = None

    @property
    def armed(self) -> Fault | None:
        return self._armed.fault if self._armed else None

    def _take(self, *kinds: Fault) -> _Armed | None:
        """Consume the armed fault if it is one of `kinds`.

        Scoped by kind so that arming "fail the next renewal" does not also
        break the purchase the demo runs first — the faults name §30.3 states,
        and a state machine that applied the wrong one would demonstrate the
        wrong screen.
        """
        armed = self._armed
        if armed is None or armed.fault not in kinds:
            return None
        if not armed.sticky:
            self._armed = None
        return armed

    def _next_ref(self, prefix: str) -> str:
        self._seq += 1
        return f"sim_{prefix}_{self._seq:06d}"

    # -- PaymentProvider ----------------------------------------------------

    async def open_purchase(self, request: PurchaseRequest) -> PurchaseIntent:
        if self._take(Fault.RAIL_DOWN) is not None:
            raise PaymentProviderUnavailable("simulated rail is down")

        provider_ref = self._next_ref("pi")
        self._intents[provider_ref] = request

        declined = self._take(Fault.DECLINE)
        if declined is not None:
            return PurchaseIntent(
                provider=self.name,
                provider_ref=provider_ref,
                checkout_url=None,
                pending=False,
                failure_reason=declined.reason,
            )

        pending = self._take(Fault.HOLD_PENDING) is not None
        return PurchaseIntent(
            provider=self.name,
            provider_ref=provider_ref,
            # Where a hosted rail page would be. The dev surface stands in for
            # it, which is the same shape: the user leaves, and we learn what
            # happened from an event rather than from the redirect.
            checkout_url=f"/dev/payments/approve/{provider_ref}",
            pending=pending,
        )

    async def charge_renewal(
        self, request: PurchaseRequest, *, provider_ref: str
    ) -> PurchaseIntent:
        if self._take(Fault.RAIL_DOWN) is not None:
            raise PaymentProviderUnavailable("simulated rail is down")

        failed = self._take(Fault.FAIL_RENEWAL)
        if failed is not None:
            return PurchaseIntent(
                provider=self.name,
                provider_ref=provider_ref,
                checkout_url=None,
                pending=False,
                failure_reason=failed.reason,
            )
        new_ref = self._next_ref("rnw")
        self._intents[new_ref] = request
        return PurchaseIntent(
            provider=self.name, provider_ref=new_ref, checkout_url=None, pending=False
        )

    async def refund(self, request: RefundRequest) -> ProviderEvent:
        if self._take(Fault.RAIL_DOWN) is not None:
            raise PaymentProviderUnavailable("simulated rail is down")
        return ProviderEvent(
            provider_event_id=self._next_ref("rfnd"),
            kind=EventKind.REFUND_SUCCEEDED,
            provider_ref=request.provider_ref,
            idempotency_key=request.idempotency_key,
            # §30.3: "refunds always return through the original rail in the
            # original currency". The amount comes back exactly as it went out,
            # negated — there is no conversion to get wrong because `Money`
            # has no operation that could perform one.
            amount=request.amount.negated(),
            occurred_at=_UTC_SENTINEL,
        )

    async def cancel_mandate(self, *, provider_ref: str) -> None:
        # Deliberately succeeds even when a fault is armed. §30.3 promises
        # cancellation is "one screen, immediate confirm" with "no retention
        # labyrinth", and a rail outage that could block a cancellation would
        # be a retention labyrinth that nobody designed and nobody could see.
        self._intents.pop(provider_ref, None)

    def verify_webhook(self, *, payload: bytes, signature: str) -> ProviderEvent:
        """Real HMAC over the real bytes. See the module header.

        `compare_digest`, not `==`: a timing-safe comparison is the entire
        point of doing this properly, and the wrong one here would be a
        plausible-looking check that leaks the signature a byte at a time.
        """
        expected = hmac.new(SIMULATOR_WEBHOOK_SECRET, payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise PaymentProviderUnavailable(
                "webhook signature verification failed (§13) — the delivery is "
                "not authenticated and grants nothing"
            )
        body = json.loads(payload)
        return ProviderEvent(
            provider_event_id=body["provider_event_id"],
            kind=EventKind(body["kind"]),
            provider_ref=body["provider_ref"],
            idempotency_key=body.get("idempotency_key"),
            amount=(
                Money(int(body["amount"]["minor"]), Currency(body["amount"]["currency"]))
                if body.get("amount")
                else None
            ),
            occurred_at=dt.datetime.fromisoformat(body["occurred_at"]),
            failure_reason=(
                PaymentFailureReason(body["failure_reason"])
                if body.get("failure_reason")
                else None
            ),
            instrument_ref=body.get("instrument_ref"),
            invoice_ref=body.get("invoice_ref"),
        )

    # -- the demo's own affordance -----------------------------------------

    def sign(self, body: dict[str, object]) -> tuple[bytes, str]:
        """Produce a delivery this rail will accept.

        Used by the dev control surface to POST a webhook the way a rail would.
        It exists so the demo goes through `verify_webhook` rather than around
        it — a control surface that called `handle_event` directly would leave
        the signature path unexercised, which is exactly the property this
        simulator was built to keep exercised.
        """
        payload = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        signature = hmac.new(SIMULATOR_WEBHOOK_SECRET, payload, hashlib.sha256).hexdigest()
        return payload, signature


#: `refund()` has no clock of its own and no caller passes one. Rather than
#: reach for `datetime.now()` — which would make the one function in this
#: package that reads a wall clock the one that stamps a financial record —
#: the sentinel is replaced by the service, which has the injected `now` every
#: other path here uses.
_UTC_SENTINEL = dt.datetime(1970, 1, 1, tzinfo=dt.UTC)
