"""§30.3's flows, over the adapter and the store.

**This module never names a rail.** Not once — no `if provider is RAZORPAY`, no
`if simulated`, nothing. It holds a `PaymentProvider` and calls the five
methods on it, which is what makes the promise in `providers/routing.py`'s
header true rather than aspirational: landing Razorpay is one matrix cell plus
an adapter class, and nothing here changes.

── The order of operations, and what each one costs to get wrong ───────────

Two rules, and both are the same rule other modules in this service learned the
hard way about something irreplaceable (`voice/service.py` stores audio before
transcribing; `calls/service.py` commits the transcript before answering):

**1. The financial row is written BEFORE the entitlement is granted.** A crash
between them leaves a payment we recorded and access we did not grant — which
is recoverable, because the row is there to reconcile against (§14's <0.1%
target reads exactly this). The other order leaves access granted against no
record: invisible, unreconcilable, and indistinguishable from fraud.

**2. `read` projects §22.13's clock on every call and writes back what it
finds.** A sweep is not what advances a subscription; the sweep is an
optimisation for rows nobody reads. Depending on it would mean a user who
opened the app on day 8 of a grace saw whatever the last sweep left behind, and
a sweep that had not run since day 6 would hand her full access for free — or,
in the direction that actually matters, a sweep that ran ahead of a recovery
would lock out someone who had already paid.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, replace
from typing import Any

from bson import ObjectId
from sitara_schemas.payments import (
    ANNUAL_REFUND_WINDOW_DAYS,
    BillingRegion,
    GiftRedemptionOutcome,
    PaymentFailureReason,
    PaymentState,
    PlanId,
    SubscriptionStatus,
)
from sitara_schemas.today import PlanState

from sitara_api.payments import lifecycle
from sitara_api.payments.gifting import (
    GIFT_ACTIVATED_KEY,
    GIFT_CONVERTED_KEY,
    GIFT_VALIDITY_DAYS,
    Gift,
    Redemption,
    mint_code,
    refusal,
)
from sitara_api.payments.lifecycle import AccessLevel
from sitara_api.payments.money import Money, Price, price_for
from sitara_api.payments.providers.base import (
    EventKind,
    PaymentProvider,
    PaymentProviderName,
    ProviderEvent,
    PurchaseIntent,
    PurchaseRequest,
    RefundRequest,
)
from sitara_api.payments.providers.routing import is_simulated
from sitara_api.payments.store import PaymentStore, StoredSubscription

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PurchaseHandle:
    """What a caller does next after `start_purchase`.

    Carries the rail's `checkout_url` (where the user enters an instrument we
    never see) and, for the simulator, the ability to mint the event the rail
    would post back. On a real rail that event arrives over the webhook and
    `authorisation_event` is never called — which is why it is on the HANDLE
    rather than on the service: the shape says "this is how the simulated rail
    completes a purchase", not "this is how purchases complete".
    """

    provider: PaymentProviderName
    provider_ref: str
    checkout_url: str | None
    pending: bool
    amount: Money
    idempotency_key: str
    failure_reason: PaymentFailureReason | None = None

    @property
    def succeeded(self) -> bool:
        return self.failure_reason is None

    def authorisation_event(self, *, now: dt.datetime) -> ProviderEvent:
        """The event a rail would post once the user has authorised."""
        return ProviderEvent(
            provider_event_id=f"sim_evt_{self.provider_ref}",
            kind=EventKind.PAYMENT_SUCCEEDED,
            provider_ref=self.provider_ref,
            idempotency_key=self.idempotency_key,
            amount=self.amount,
            occurred_at=now,
            instrument_ref=f"tok_{self.provider_ref}",
            invoice_ref=f"inv_{self.provider_ref}",
        )


@dataclass(frozen=True)
class EventOutcome:
    """What `handle_event` did, in terms a caller can act on."""

    applied: bool
    duplicate: bool = False
    #: §30.3's "auto-refund duplicate with notice" — a genuinely second charge,
    #: reversed. Distinct from `duplicate`, which is a redelivery we ignored.
    refunded_duplicate: bool = False


@dataclass(frozen=True)
class SubscriptionView:
    """S30's payload, and the entitlement check's answer, in one value.

    `status` is None for a user who has never subscribed — a real state, and
    not the same as `downgraded`. Somebody who never bought and somebody whose
    §22.13 ladder ran out get different screens (§28.2 gives the second one a
    "your memories are safe" history the first has none of), and a default
    status would have made them one.
    """

    status: SubscriptionStatus | None
    access: AccessLevel
    plan_state: PlanState
    plan: PlanId | None = None
    region: BillingRegion | None = None
    price: Money | None = None
    period_start: dt.datetime | None = None
    period_end: dt.datetime | None = None
    renewal_failed_at: dt.datetime | None = None
    grace_ends_at: dt.datetime | None = None
    downgrades_at: dt.datetime | None = None
    mandate_retry_required: bool = False
    founding: bool = False
    #: §22.13's "no hard deletion", asserted from outside rather than assumed.
    retains_history: bool = True
    #: Whether the rail that took this money moves any. S30 renders a banner
    #: from it — see `routing.is_simulated`.
    simulated: bool = False
    #: §30.3's migration offer: set only AT renewal, never mid-cycle.
    region_switch_offered: bool = False


class PaymentService:
    def __init__(self, db: Any, provider: PaymentProvider) -> None:
        self._db = db
        self._store = PaymentStore(db)
        self._provider = provider

    @property
    def simulated(self) -> bool:
        """Whether the rail behind this service moves any money.

        A boolean about the DEPLOYMENT, not a vendor name — see the router's
        header for why no endpoint returns the latter. Exposed so surfaces that
        show a receipt can carry §30.3's honesty line without reaching into
        `_provider`; `read()` already puts the same value on `SubscriptionView`.
        """
        return is_simulated(self._provider.name)

    # -- purchase ----------------------------------------------------------

    async def start_purchase(
        self,
        *,
        user_id: str,
        plan: PlanId,
        region: BillingRegion,
        idempotency_key: str,
        now: dt.datetime,
        founding: bool = False,
        locale: str = "en",
    ) -> PurchaseHandle:
        """§30.3's plan-select → rail-handoff.

        Nothing is granted here. The rail is asked to collect; the grant
        happens in `handle_event` when it says it did.
        """
        price = price_for(region, plan, founding=founding)
        intent = await self._provider.open_purchase(
            PurchaseRequest(
                user_id=user_id,
                plan=plan,
                region=region,
                amount=price.amount,
                idempotency_key=idempotency_key,
                locale=locale,
            )
        )

        if intent.failure_reason is not None:
            # A declined FIRST payment is not a lapsed subscriber. There is no
            # row to put in grace, because nothing was ever granted — S34
            # renders the failure and S31 is still where she goes next.
            return _handle(intent, price, idempotency_key)

        if intent.pending:
            # §30.3's 5-minute UPI hold. The row exists so a second purchase
            # cannot start beside it (`live` covers `pending`), and grants
            # nothing (`_ACCESS[PENDING]` is NONE).
            await self._store.upsert(
                user_id=user_id,
                state=lifecycle.start(
                    plan=plan,
                    region=region,
                    now=now,
                    term_days=price.term_days,
                    founding=founding,
                    pending=True,
                ),
                provider=self._provider.name,
                price=price.amount,
                provider_sub_id=intent.provider_ref,
                now=now,
            )
        else:
            # Authorised but not yet confirmed: the rail will post an event.
            # Recorded as pending for the same reason — the slot is taken.
            await self._store.upsert(
                user_id=user_id,
                state=lifecycle.start(
                    plan=plan,
                    region=region,
                    now=now,
                    term_days=price.term_days,
                    founding=founding,
                    pending=True,
                ),
                provider=self._provider.name,
                price=price.amount,
                provider_sub_id=intent.provider_ref,
                now=now,
            )
        return _handle(intent, price, idempotency_key)

    # -- the webhook door --------------------------------------------------

    async def handle_event(
        self,
        event: ProviderEvent,
        *,
        now: dt.datetime,
        _skip_precheck: bool = False,
    ) -> EventOutcome:
        """One rail event, applied at most once (§30.3).

        `_skip_precheck` exists for one test, which forces the check-then-write
        race by removing the check. It is named with a leading underscore
        because it is not an option: the guard that must hold is the unique
        index, and the pre-check is only an optimisation that avoids a wasted
        insert. A caller reaching for this in production would be removing
        nothing that protects anything.
        """
        # **A rail event carries no user id, and it must not.** §13 keeps our
        # identifiers out of a vendor's system; the join is the rail reference
        # that `start_purchase` stored on the row. A webhook that named a user
        # would be a webhook whose forger could name one too — the signature
        # is what authenticates the delivery, and the row is what says whose
        # it is.
        stored = await self._store.find_by_provider_ref(event.provider_ref)
        if stored is None:
            logger.warning(
                "rail event %s matches no subscription; ignored",
                event.provider_event_id,
            )
            return EventOutcome(applied=False)
        user_id = stored.user_id

        # ── The two duplicate questions, in the order they must be asked ────
        #
        # 1. Is this the SAME event again (a redelivery)?  → ignore it.
        # 2. Is this a DIFFERENT event that charged for the same purchase?
        #    → §30.3: "auto-refund duplicate with notice".
        #
        # The order is load-bearing and was wrong first time round: asking (2)
        # first makes every redelivery of a successful charge look like a
        # second charge, so the rail's ordinary retry would trigger a refund
        # and hand the money back to a user who had paid exactly once. (1) is
        # the cheap, certain question and it goes first.
        if not _skip_precheck and await self._already_seen(event):
            return EventOutcome(applied=False, duplicate=True)

        recorded = await self._store.record_event(
            user_id=user_id,
            provider=self._provider.name,
            event=event,
            state=_state_of(event).value,
            subscription_id=stored.id,
            simulated=is_simulated(self._provider.name),
            now=now,
        )
        if not recorded:
            # The index refused it — a concurrent worker won the race. This is
            # the guard that actually holds; the pre-check above only saves a
            # wasted insert. `_skip_precheck` exists so a test can prove it.
            return EventOutcome(applied=False, duplicate=True)

        # Question (2). Asked AFTER the row is written, and excluding the row
        # we just wrote: the charge genuinely happened, so §6.4's ledger must
        # carry it (8 years, tax) — what §30.3 reverses is the money, not the
        # record. A check that ran before the insert would have to choose
        # between recording a charge it was about to refund and losing it.
        if (
            event.kind is EventKind.PAYMENT_SUCCEEDED
            and event.idempotency_key
            and await self._store.has_other_charge(
                idempotency_key=event.idempotency_key,
                excluding_event_id=event.provider_event_id,
            )
        ):
            return await self._refund_duplicate(
                user_id=user_id, event=event, subscription_id=stored.id, now=now
            )

        await self._apply(stored, event, user_id=user_id, now=now)
        return EventOutcome(applied=True)

    async def _apply(
        self,
        stored: StoredSubscription,
        event: ProviderEvent,
        *,
        user_id: str,
        now: dt.datetime,
    ) -> None:
        """Turn a recorded event into a state change. §22.13's transitions."""
        state = stored.state
        price = _price_of(stored)

        if event.kind is EventKind.PAYMENT_SUCCEEDED:
            if state.status is SubscriptionStatus.PENDING:
                state = lifecycle.settle_pending(state, now=now, term_days=price.term_days)
            else:
                state = lifecycle.renew(state, term_days=price.term_days)
        elif event.kind in (EventKind.PAYMENT_FAILED, EventKind.RENEWAL_FAILED):
            state = lifecycle.fail_renewal(
                state, reason=event.failure_reason or PaymentFailureReason.UNKNOWN, now=now
            )
        elif event.kind is EventKind.MANDATE_REJECTED:
            state = lifecycle.reject_mandate(state)
        elif event.kind is EventKind.REFUND_SUCCEEDED:
            # §22.16's refund ends the subscription at the moment of refund:
            # she has her money back, so she is not paying for a period.
            state = replace(state, status=SubscriptionStatus.EXPIRED, period_end=now)

        await self._store.upsert(
            user_id=user_id,
            state=state,
            provider=self._provider.name,
            price=stored.price,
            provider_sub_id=stored.provider_sub_id,
            now=now,
            subscription_id=stored.id,
        )

    async def _already_seen(self, event: ProviderEvent) -> bool:
        return (
            await self._db.payments.count_documents(
                {"provider_event_id": event.provider_event_id}, limit=1
            )
            > 0
        )

    async def _refund_duplicate(
        self,
        *,
        user_id: str,
        event: ProviderEvent,
        subscription_id: ObjectId,
        now: dt.datetime,
    ) -> EventOutcome:
        """§30.3: "double-webhook reconciled, auto-refund duplicate with notice".

        The refund row is written even though nothing about the subscription
        changes — §6.4 keeps `payments` for 8 years and a charge we reversed is
        exactly what an auditor comes looking for. Silently discarding it would
        leave the rail's ledger and ours permanently apart, which is the number
        §14's <0.1% reconciliation target measures.
        """
        assert event.amount is not None
        reversal = await self._provider.refund(
            RefundRequest(
                provider_ref=event.provider_event_id,
                amount=event.amount,
                idempotency_key=event.idempotency_key or event.provider_event_id,
            )
        )
        # The reversal keeps its OWN rail event id: the duplicate charge is
        # already in the ledger under its own, and §6.4 retains both for 8
        # years. Two rows, because two things happened.
        await self._store.record_event(
            user_id=user_id,
            provider=self._provider.name,
            event=replace(
                reversal,
                provider_ref=event.provider_ref,
                occurred_at=now,
            ),
            state=PaymentState.REFUNDED.value,
            subscription_id=subscription_id,
            simulated=is_simulated(self._provider.name),
            now=now,
        )
        return EventOutcome(applied=False, refunded_duplicate=True)

    # -- §22.13's lifecycle ------------------------------------------------

    async def record_renewal_failure(
        self, *, user_id: str, reason: PaymentFailureReason, now: dt.datetime
    ) -> SubscriptionView:
        """The renewal sweep's per-user step, when the rail could not collect."""
        stored = await self._store.find_live(user_id)
        if stored is None:
            return await self.read(user_id=user_id, now=now)
        await self._store.upsert(
            user_id=user_id,
            state=lifecycle.fail_renewal(stored.state, reason=reason, now=now),
            provider=self._provider.name,
            price=stored.price,
            provider_sub_id=stored.provider_sub_id,
            now=now,
            subscription_id=stored.id,
        )
        return await self.read(user_id=user_id, now=now)

    async def record_mandate_rejected(
        self, *, user_id: str, now: dt.datetime
    ) -> SubscriptionView:
        """§30.3 — the charge succeeded and the standing instruction did not."""
        stored = await self._store.find_live(user_id)
        if stored is not None:
            await self._store.upsert(
                user_id=user_id,
                state=lifecycle.reject_mandate(stored.state),
                provider=self._provider.name,
                price=stored.price,
                provider_sub_id=stored.provider_sub_id,
                now=now,
                subscription_id=stored.id,
            )
        return await self.read(user_id=user_id, now=now)

    async def retry_renewal(
        self, *, user_id: str, idempotency_key: str, now: dt.datetime
    ) -> PurchaseHandle:
        """§22.13's "one-tap alternate-payment retry"."""
        stored = await self._store.find_live(user_id)
        if stored is None:
            raise NoSubscription(f"no live subscription for {user_id}")
        price = _price_of(stored)
        intent = await self._provider.charge_renewal(
            PurchaseRequest(
                user_id=user_id,
                plan=stored.state.plan,
                region=stored.state.region,
                amount=price.amount,
                idempotency_key=idempotency_key,
            ),
            provider_ref=stored.provider_sub_id or "",
        )
        # The retry's new rail reference has to be findable when its event
        # arrives, so the row points at it.
        await self._store.upsert(
            user_id=user_id,
            state=stored.state,
            provider=self._provider.name,
            price=stored.price,
            provider_sub_id=intent.provider_ref,
            now=now,
            subscription_id=stored.id,
        )
        return _handle(intent, price, idempotency_key)

    async def cancel(self, *, user_id: str, now: dt.datetime) -> SubscriptionView:
        """§30.3: one screen, immediate confirm, access till period end.

        The rail is told AFTER our state changes, and a rail failure is logged
        rather than raised. §30.3 forbids a retention labyrinth, and a
        cancellation a user could not complete because a vendor was down is a
        retention labyrinth nobody designed and nobody could see.
        """
        stored = await self._store.find_live(user_id)
        if stored is None:
            return await self.read(user_id=user_id, now=now)
        await self._store.upsert(
            user_id=user_id,
            state=lifecycle.cancel(stored.state),
            provider=self._provider.name,
            price=stored.price,
            provider_sub_id=stored.provider_sub_id,
            now=now,
            subscription_id=stored.id,
        )
        try:
            await self._provider.cancel_mandate(provider_ref=stored.provider_sub_id or "")
        except Exception:  # noqa: BLE001 — see the docstring
            logger.warning(
                "rail refused the mandate cancellation; the subscription is cancelled "
                "regardless (§30.3 — immediate confirm, no retention labyrinth)"
            )
        return await self.read(user_id=user_id, now=now)

    async def refund(
        self, *, user_id: str, now: dt.datetime
    ) -> Redemption | SubscriptionView:
        """§22.16's 7-day no-questions window, annual only.

        The window is a POLICY and the refusal says so — `PAY_REFUND_WINDOW_CLOSED`
        is a 422 rather than a 403, because the caller is entitled to ask and
        the answer is about the policy rather than about them.
        """
        stored = await self._store.find_live(user_id)
        if stored is None:
            raise NoSubscription(f"no live subscription for {user_id}")
        if stored.state.plan is not PlanId.ANNUAL:
            raise RefundWindowClosed(
                "§22.16 grants the 7-day no-questions window to ANNUAL plans. "
                "Extending it to monthly here would be a policy decision made in code."
            )
        if now > stored.state.period_start + dt.timedelta(days=ANNUAL_REFUND_WINDOW_DAYS):
            raise RefundWindowClosed(
                f"§22.16's window is {ANNUAL_REFUND_WINDOW_DAYS} days from the purchase"
            )
        assert stored.price is not None
        reversal = await self._provider.refund(
            RefundRequest(
                provider_ref=stored.provider_sub_id or "",
                # §30.3: "refunds always return through the original rail in the
                # original currency". `stored.price` IS that currency, and
                # `Money` has no operation that could convert it.
                amount=stored.price,
                idempotency_key=f"refund-{stored.id}",
            )
        )
        await self._store.record_event(
            user_id=user_id,
            provider=self._provider.name,
            event=replace(reversal, occurred_at=now),
            state=PaymentState.REFUNDED.value,
            subscription_id=stored.id,
            simulated=is_simulated(self._provider.name),
            now=now,
        )
        await self._store.upsert(
            user_id=user_id,
            state=replace(stored.state, status=SubscriptionStatus.EXPIRED, period_end=now),
            provider=self._provider.name,
            price=stored.price,
            provider_sub_id=stored.provider_sub_id,
            now=now,
            subscription_id=stored.id,
        )
        return await self.read(user_id=user_id, now=now)

    # -- gifting -----------------------------------------------------------

    async def purchase_gift(
        self,
        *,
        buyer_user_id: str,
        plan: PlanId,
        region: BillingRegion,
        idempotency_key: str,
        now: dt.datetime,
    ) -> Gift:
        """§30.3's S32. The gift is a sale to the BUYER's region (§22.1)."""
        price = price_for(region, plan)
        gift = Gift(
            code=mint_code(),
            buyer_user_id=buyer_user_id,
            plan=plan,
            region=region,
            value=price.amount,
            term_days=price.term_days,
            purchased_at=now,
            expires_at=now + dt.timedelta(days=GIFT_VALIDITY_DAYS),
        )
        await self._store.put_gift(gift, now=now)
        return gift

    async def redeem_gift(
        self, *, user_id: str, code: str, now: dt.datetime
    ) -> Redemption:
        """§30.3's S33, all five outcomes.

        The middle one is arithmetic: an existing subscription is EXTENDED by
        the gifted term. See `gifting.py`'s header for why the extension is in
        days and not in money.
        """
        gift = await self._store.find_gift(code)
        if gift is None:
            return refusal(GiftRedemptionOutcome.INVALID)
        blocked = gift.redeemable_at(now)
        if blocked is not None:
            return refusal(blocked)

        existing = await self._store.find_live(user_id)
        outcome = (
            GiftRedemptionOutcome.CREDIT_CONVERTED
            if existing is not None
            else GiftRedemptionOutcome.ACTIVATED
        )

        # Compare-and-swap FIRST. Two simultaneous redemptions of one code must
        # produce one winner; claiming after extending would produce two
        # extensions from one purchase.
        if not await self._store.claim_gift(
            code=code, user_id=user_id, outcome=outcome.value, now=now
        ):
            return refusal(GiftRedemptionOutcome.ALREADY_REDEEMED)

        if existing is not None:
            # §30.3: extend. NOT replace, and NOT convert — the subscription
            # keeps its own plan, region and currency, and gains time.
            state = lifecycle.extend(existing.state, days=gift.term_days)
            stored = await self._store.upsert(
                user_id=user_id,
                state=state,
                provider=self._provider.name,
                price=existing.price,
                provider_sub_id=existing.provider_sub_id,
                now=now,
                subscription_id=existing.id,
            )
            return Redemption(
                outcome=outcome,
                message_key=GIFT_CONVERTED_KEY,
                # §30.3: "gift credits are denominated in their purchase
                # currency". Reported, never applied.
                gift_value=gift.value,
                extended_to=stored.state.period_end,
            )

        # §30.3 — "valid → onboarding with a gift banner". The new subscription
        # takes the GIFT's region, because there is no existing one to preserve.
        state = lifecycle.start(
            plan=gift.plan,
            region=gift.region,
            now=now,
            term_days=gift.term_days,
        )
        stored = await self._store.upsert(
            user_id=user_id,
            state=state,
            provider=self._provider.name,
            price=gift.value,
            provider_sub_id=None,
            now=now,
        )
        return Redemption(
            outcome=outcome,
            message_key=GIFT_ACTIVATED_KEY,
            gift_value=gift.value,
            extended_to=stored.state.period_end,
        )

    # -- region migration --------------------------------------------------

    async def migrate_region(
        self, *, user_id: str, region: BillingRegion, now: dt.datetime
    ) -> SubscriptionView:
        """§30.3's billing-region migration. Refuses mid-cycle, by design.

        The refusal is the policy: "an active subscription always retains its
        original currency and rail until renewal — no mid-cycle conversion,
        ever". `lifecycle.migrate_region` raises rather than deferring, because
        a function that accepted at any time and quietly scheduled is one whose
        callers stop knowing when it takes effect.
        """
        stored = await self._store.find_live(user_id)
        if stored is None:
            raise NoSubscription(f"no live subscription for {user_id}")
        state = lifecycle.migrate_region(stored.state, region=region, now=now)
        await self._store.upsert(
            user_id=user_id,
            state=state,
            provider=self._provider.name,
            # The PRICE is dropped: it was denominated in the old region's
            # currency and the new region's is a different one. It is
            # re-established by the renewal that follows, at the new region's
            # declared price — which §30.3 requires be "shown explicitly".
            price=None,
            provider_sub_id=None,
            now=now,
            subscription_id=stored.id,
        )
        return await self.read(user_id=user_id, now=now)

    # -- the read ----------------------------------------------------------

    async def read(self, *, user_id: str, now: dt.datetime) -> SubscriptionView:
        """S30's payload and the entitlement answer, with the clock applied.

        Projects §22.13's ladder and WRITES BACK what it finds — see rule 2 in
        the module header. Never depends on a sweep having run.
        """
        stored = await self._store.find_live(user_id) or await self._store.find_latest(user_id)
        if stored is None:
            return SubscriptionView(
                status=None, access=AccessLevel.NONE, plan_state=PlanState.FREE
            )

        projected = stored.state.project(now)
        if projected.status is not stored.state.status:
            await self._store.upsert(
                user_id=user_id,
                state=projected,
                provider=stored.provider,
                price=stored.price,
                provider_sub_id=stored.provider_sub_id,
                now=now,
                subscription_id=stored.id,
            )

        return SubscriptionView(
            status=projected.status,
            access=projected.access_at(now),
            plan_state=projected.plan_state_at(now),
            plan=projected.plan,
            region=projected.region,
            price=stored.price,
            period_start=projected.period_start,
            period_end=projected.period_end,
            renewal_failed_at=projected.renewal_failed_at,
            grace_ends_at=projected.read_only_at,
            downgrades_at=projected.downgrade_at,
            mandate_retry_required=projected.mandate_retry_required,
            founding=projected.founding,
            retains_history=projected.retains_history,
            simulated=is_simulated(stored.provider),
            # §30.3: the switch is offered AT renewal, never mid-cycle. Which
            # is exactly when `migrate_region` would stop refusing.
            region_switch_offered=now >= projected.period_end,
        )


class NoSubscription(LookupError):
    """An operation that needs a live subscription found none."""


class RefundWindowClosed(ValueError):
    """§22.16's window does not cover this. Maps to PAY_REFUND_WINDOW_CLOSED."""


# ---------------------------------------------------------------------------


def _handle(intent: PurchaseIntent, price: Price, idempotency_key: str) -> PurchaseHandle:
    return PurchaseHandle(
        provider=intent.provider,
        provider_ref=intent.provider_ref,
        checkout_url=intent.checkout_url,
        pending=intent.pending,
        amount=price.amount,
        idempotency_key=idempotency_key,
        failure_reason=intent.failure_reason,
    )


def _price_of(stored: StoredSubscription) -> Price:
    """The price this subscription renews at.

    Read from the price book by (region, plan) rather than from the stored
    amount, because the stored amount is what she paid LAST time and a renewal
    is a new sale at the current price. The stored amount is what a receipt
    shows; this is what the next charge is.
    """
    return price_for(stored.state.region, stored.state.plan, founding=stored.state.founding)


def _state_of(event: ProviderEvent) -> PaymentState:
    return {
        EventKind.PAYMENT_SUCCEEDED: PaymentState.SUCCEEDED,
        EventKind.PAYMENT_FAILED: PaymentState.FAILED,
        EventKind.RENEWAL_FAILED: PaymentState.FAILED,
        EventKind.MANDATE_REJECTED: PaymentState.FAILED,
        EventKind.REFUND_SUCCEEDED: PaymentState.REFUNDED,
    }[event.kind]
