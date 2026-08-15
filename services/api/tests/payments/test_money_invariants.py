"""The three money invariants that survive the simulator (§30.3, §22.13, §22.16).

A simulator removes the vendor and removes nothing else. Every rule this file
checks is ours: it lives in `payments.lifecycle`, `payments.gifting` and
`payments.service`, and swapping the simulator for Razorpay would not move a
single assertion here. That is the test for whether a prototype's tests were
worth writing — if the answer changes when the rail becomes real, the test was
about the rail.

So these three, and no more, because these three are the ones where being
wrong costs a user money or access:

  1. **A double webhook grants once.** Two deliveries of one event is the
     normal case, not the pathological one — every rail retries, and §30.3
     names the guard ("idempotency keys; double-webhook reconciled").
  2. **A failed renewal never revokes access before the grace period ends.**
     §22.13's whole promise is that nothing is taken away at the moment the
     money fails.
  3. **A gift to an existing subscriber extends rather than replaces.** §30.3's
     "already-subscribed → credit conversion". The giver bought time; she
     already had time; the two add.

**Every test asserts what must NOT change as hard as what does**, following
`tests/memory/test_deletion_paths.py`. In money code the negatives are where
the damage is: a period silently shortened, a currency silently converted, a
row silently replaced. All three are invisible in a green suite that only
checks the value it expected to see.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sitara_schemas.payments import (
    GRACE_PERIOD_DAYS,
    READ_ONLY_PERIOD_DAYS,
    BillingRegion,
    Currency,
    GiftRedemptionOutcome,
    PaymentFailureReason,
    PlanId,
    SubscriptionStatus,
)

from sitara_api.payments.lifecycle import AccessLevel
from sitara_api.payments.money import Money
from sitara_api.payments.providers.base import EventKind, ProviderEvent
from sitara_api.payments.providers.simulator import Fault, SimulatedRail
from sitara_api.payments.service import PaymentService, SubscriptionView
from tests.payments.conftest import GIVER_ID, NOW, USER_ID

pytestmark = pytest.mark.asyncio


def _period_end(view: SubscriptionView) -> dt.datetime:
    """The period end, narrowed. See `_subscribed`."""
    assert view.period_end is not None
    return view.period_end


async def _subscribed(
    service: PaymentService,
    *,
    plan: PlanId = PlanId.ANNUAL,
    region: BillingRegion = BillingRegion.INDIA,
    now: dt.datetime = NOW,
) -> SubscriptionView:
    """A user who has actually paid, through the real purchase path.

    Deliberately not a hand-written `subscriptions` document. A fixture that
    inserted the row directly would let every test below pass against a service
    whose purchase path wrote something else entirely — which is exactly the
    class of defect §6.4's validators exist to catch and a hand-rolled document
    walks straight past.
    """
    handle = await service.start_purchase(
        user_id=str(USER_ID),
        plan=plan,
        region=region,
        idempotency_key=f"idem-{plan.value}-{region.value}",
        now=now,
    )
    await service.handle_event(handle.authorisation_event(now=now), now=now)
    view = await service.read(user_id=str(USER_ID), now=now)
    # `SubscriptionView.period_end` is Optional because a user who never
    # subscribed has none. This helper's whole job is producing one who did, so
    # the narrowing happens once here rather than at every arithmetic site
    # below — and if a purchase ever stops setting a period, every test that
    # depends on one fails at the same readable line.
    assert view.period_end is not None
    return view


# ---------------------------------------------------------------------------
# 1. A double webhook grants once
# ---------------------------------------------------------------------------


async def test_a_replayed_webhook_grants_once(service: PaymentService, db) -> None:  # noqa: ANN001
    """The same `provider_event_id` twice: applied once, recorded once, and —
    the assertion that matters — the period is not extended twice."""
    handle = await service.start_purchase(
        user_id=str(USER_ID),
        plan=PlanId.MONTHLY,
        region=BillingRegion.INDIA,
        idempotency_key="idem-double",
        now=NOW,
    )
    event = handle.authorisation_event(now=NOW)

    first = await service.handle_event(event, now=NOW)
    after_first = await service.read(user_id=str(USER_ID), now=NOW)

    # The rail redelivers a minute later, as every rail eventually does.
    second = await service.handle_event(event, now=NOW + dt.timedelta(minutes=1))
    after_second = await service.read(user_id=str(USER_ID), now=NOW + dt.timedelta(minutes=1))

    assert first.applied is True
    assert second.applied is False
    assert second.duplicate is True

    # ── What must NOT change ────────────────────────────────────────────────
    # The period is the money. A second application would silently hand this
    # user a free month, and nothing on any screen would look wrong.
    assert after_second.period_end == after_first.period_end
    assert after_second.period_start == after_first.period_start
    assert after_second.status is after_first.status is SubscriptionStatus.ACTIVE

    # One financial row per provider event (§6.4's `provider_event_id` uniq).
    assert await db.payments.count_documents({"provider_event_id": event.provider_event_id}) == 1
    # And one subscription, not two — the duplicate must not have minted a row.
    assert await db.subscriptions.count_documents({"user_id": USER_ID}) == 1


async def test_the_duplicate_guard_is_the_index_and_not_only_the_read(
    service: PaymentService, db  # noqa: ANN001
) -> None:
    """The check-then-write race, forced.

    `handle_event` reads before it writes, and between the read and the write
    is where two webhook deliveries in two workers actually collide. This test
    removes the read — it inserts the row the way a concurrent worker would
    have — and asserts the SECOND write is refused by the database rather than
    by the application. §30.3's guarantee has to hold under concurrency or it
    is a guarantee about single-threaded test runs.
    """
    handle = await service.start_purchase(
        user_id=str(USER_ID),
        plan=PlanId.MONTHLY,
        region=BillingRegion.INDIA,
        idempotency_key="idem-race",
        now=NOW,
    )
    event = handle.authorisation_event(now=NOW)
    await service.handle_event(event, now=NOW)

    before = await service.read(user_id=str(USER_ID), now=NOW)
    # The competing worker's delivery, arriving with the read already stale.
    outcome = await service.handle_event(event, now=NOW, _skip_precheck=True)
    after = await service.read(user_id=str(USER_ID), now=NOW)

    assert outcome.applied is False
    assert outcome.duplicate is True
    assert after.period_end == before.period_end
    assert await db.payments.count_documents({"provider_event_id": event.provider_event_id}) == 1


async def test_a_duplicate_CHARGE_is_refunded_and_the_period_is_not_extended(
    service: PaymentService, db  # noqa: ANN001
) -> None:
    """§30.3's other duplicate: two DIFFERENT event ids for one charge.

    The idempotency key catches the redelivery; it cannot catch a rail that
    genuinely charged twice, which §30.3 handles differently — "auto-refund
    duplicate with notice". Two distinct `provider_event_id`s carrying the same
    idempotency key is that case, and the second must reverse rather than
    stack.
    """
    handle = await service.start_purchase(
        user_id=str(USER_ID),
        plan=PlanId.MONTHLY,
        region=BillingRegion.INDIA,
        idempotency_key="idem-twice-charged",
        now=NOW,
    )
    await service.handle_event(handle.authorisation_event(now=NOW), now=NOW)
    granted = await service.read(user_id=str(USER_ID), now=NOW)

    # A second event, for the SAME purchase — which is what a rail that
    # genuinely charged twice emits. Distinct event id, same `provider_ref`,
    # same idempotency key: the index cannot see it and the key can.
    second_charge = ProviderEvent(
        provider_event_id="sim_evt_a_different_id",
        kind=EventKind.PAYMENT_SUCCEEDED,
        provider_ref=handle.provider_ref,
        idempotency_key="idem-twice-charged",
        amount=Money(49900, Currency.INR),
        occurred_at=NOW + dt.timedelta(seconds=30),
    )
    outcome = await service.handle_event(second_charge, now=NOW + dt.timedelta(seconds=30))
    after = await service.read(user_id=str(USER_ID), now=NOW + dt.timedelta(seconds=30))

    assert outcome.applied is False
    assert outcome.refunded_duplicate is True

    # ── What must NOT change ────────────────────────────────────────────────
    assert after.period_end == granted.period_end

    # The refund is a real financial row, not a silent discard: §6.4 retains
    # `payments` for 8 years and a charge we reversed is exactly the kind of
    # thing an auditor comes looking for.
    refunds = await db.payments.count_documents(
        {"provider_event_id": second_charge.provider_event_id}
    )
    assert refunds == 1


# ---------------------------------------------------------------------------
# 2. A failed renewal never revokes access before the grace period ends
# ---------------------------------------------------------------------------


async def test_a_failed_renewal_keeps_full_access_for_the_whole_grace(
    service: PaymentService,
) -> None:
    """§22.13 day by day. Seven days, and full access on every one of them.

    Sampled at every single day rather than at the ends, because the failure
    this guards against is not "grace does not work" — it is an off-by-one that
    revokes on day 6, which a two-point test cannot see.
    """
    before = await _subscribed(service, plan=PlanId.MONTHLY)
    failed_at = _period_end(before)

    await service.record_renewal_failure(
        user_id=str(USER_ID),
        reason=PaymentFailureReason.INSUFFICIENT_FUNDS,
        now=failed_at,
    )

    for day in range(GRACE_PERIOD_DAYS):
        at = failed_at + dt.timedelta(days=day, hours=12)
        view = await service.read(user_id=str(USER_ID), now=at)
        assert view.status is SubscriptionStatus.GRACE, f"day {day}"
        # The whole point. Not "some" access, not "reduced" access.
        assert view.access is AccessLevel.FULL, f"day {day}"

        # ── What must NOT change, at any point in the grace ─────────────────
        assert view.plan is before.plan
        assert view.region is before.region
        assert view.price == before.price
        # The period she paid for is a fact about a completed transaction. A
        # failed renewal is a fact about the NEXT one and must not rewrite it.
        assert view.period_end == before.period_end


async def test_grace_ends_exactly_on_the_seventh_day_and_becomes_read_only(
    service: PaymentService,
) -> None:
    """The boundary, from both sides, and what read-only still guarantees."""
    before = await _subscribed(service, plan=PlanId.MONTHLY)
    failed_at = _period_end(before)
    await service.record_renewal_failure(
        user_id=str(USER_ID), reason=PaymentFailureReason.BANK_TIMEOUT, now=failed_at
    )

    just_inside = failed_at + dt.timedelta(days=GRACE_PERIOD_DAYS) - dt.timedelta(seconds=1)
    on_the_boundary = failed_at + dt.timedelta(days=GRACE_PERIOD_DAYS)

    assert (await service.read(user_id=str(USER_ID), now=just_inside)).access is AccessLevel.FULL
    after = await service.read(user_id=str(USER_ID), now=on_the_boundary)

    assert after.status is SubscriptionStatus.READ_ONLY
    assert after.access is AccessLevel.READ_ONLY

    # ── What must NOT change ────────────────────────────────────────────────
    # §22.13: "a 21-day read-only 'your memories are safe' state before
    # downgrade — no hard deletion". Read-only is a narrowing of what she can
    # DO, and nothing at all about what is kept.
    assert after.plan is before.plan
    assert after.region is before.region
    assert after.retains_history is True


async def test_downgrade_is_28_days_away_and_still_deletes_nothing(
    service: PaymentService,
) -> None:
    """7 + 21. The full §22.13 ladder, and its terminal state is not a delete."""
    before = await _subscribed(service, plan=PlanId.MONTHLY)
    failed_at = _period_end(before)
    await service.record_renewal_failure(
        user_id=str(USER_ID), reason=PaymentFailureReason.MANDATE_DECLINED, now=failed_at
    )

    total = GRACE_PERIOD_DAYS + READ_ONLY_PERIOD_DAYS
    day_before = failed_at + dt.timedelta(days=total) - dt.timedelta(seconds=1)
    assert (
        await service.read(user_id=str(USER_ID), now=day_before)
    ).status is SubscriptionStatus.READ_ONLY

    after = await service.read(user_id=str(USER_ID), now=failed_at + dt.timedelta(days=total))
    assert after.status is SubscriptionStatus.DOWNGRADED
    assert after.access is AccessLevel.NONE

    # ── What must NOT change ────────────────────────────────────────────────
    assert after.retains_history is True


async def test_paying_inside_the_grace_recovers_without_losing_the_anchor(
    service: PaymentService, db  # noqa: ANN001
) -> None:
    """§22.13's "one-tap alternate-payment retry", and what it restores."""
    before = await _subscribed(service, plan=PlanId.MONTHLY)
    failed_at = _period_end(before)
    await service.record_renewal_failure(
        user_id=str(USER_ID), reason=PaymentFailureReason.INSUFFICIENT_FUNDS, now=failed_at
    )

    recovered_at = failed_at + dt.timedelta(days=5)
    handle = await service.retry_renewal(
        user_id=str(USER_ID), idempotency_key="idem-recovery", now=recovered_at
    )
    await service.handle_event(handle.authorisation_event(now=recovered_at), now=recovered_at)
    after = await service.read(user_id=str(USER_ID), now=recovered_at)

    assert after.status is SubscriptionStatus.ACTIVE
    assert after.access is AccessLevel.FULL
    # The billing anchor is the ORIGINAL period end, not the day the retry
    # landed. Anchoring on the retry would walk every recovered subscriber's
    # renewal date forward by however long their bank took, permanently.
    assert after.period_start == _period_end(before)
    # And the failure is cleared, so nothing renders a stale grace banner.
    assert after.renewal_failed_at is None
    assert await db.subscriptions.count_documents({"user_id": USER_ID}) == 1


async def test_a_rejected_mandate_after_purchase_does_not_touch_the_paid_period(
    service: PaymentService,
) -> None:
    """§30.3: "mandate rejected post-purchase (subscription active on paid
    period; mandate retry flow queued)".

    The money arrived and the standing instruction for the NEXT one did not.
    Confusing the two would cancel a subscription somebody has already paid
    for, which is the most expensive way to be wrong in this file.
    """
    before = await _subscribed(service, plan=PlanId.MONTHLY)

    await service.record_mandate_rejected(user_id=str(USER_ID), now=NOW + dt.timedelta(hours=2))
    after = await service.read(user_id=str(USER_ID), now=NOW + dt.timedelta(hours=2))

    assert after.status is SubscriptionStatus.ACTIVE
    assert after.access is AccessLevel.FULL
    assert after.period_end == before.period_end
    # The only thing that changed: the renewal cannot auto-collect, and that is
    # a queued task plus a screen, not a state change.
    assert after.mandate_retry_required is True


# ---------------------------------------------------------------------------
# 3. A gift to an existing subscriber extends rather than replaces
# ---------------------------------------------------------------------------


async def test_a_gift_to_an_existing_subscriber_extends_the_period(
    service: PaymentService, db  # noqa: ANN001
) -> None:
    """§30.3's credit conversion, and the four things it must leave alone.

    The NRI case §10-20 names: bought in USD, redeemed in India, by someone who
    already subscribes. Every field below is one §30.3 states in its own
    sentence, and every one of them is silently destroyable by a redemption
    that overwrote the row instead of extending it.
    """
    before = await _subscribed(service, plan=PlanId.ANNUAL, region=BillingRegion.INDIA)
    row_before = await db.subscriptions.find_one({"user_id": USER_ID})

    gift = await service.purchase_gift(
        buyer_user_id=str(GIVER_ID),
        plan=PlanId.ANNUAL,
        region=BillingRegion.INTERNATIONAL,  # bought in USD
        idempotency_key="idem-gift",
        now=NOW,
    )
    redeemed_at = NOW + dt.timedelta(days=3)
    redemption = await service.redeem_gift(
        user_id=str(USER_ID), code=gift.code, now=redeemed_at
    )
    after = await service.read(user_id=str(USER_ID), now=redeemed_at)
    row_after = await db.subscriptions.find_one({"user_id": USER_ID})

    assert redemption.outcome is GiftRedemptionOutcome.CREDIT_CONVERTED

    # ── What DOES change: the period, by exactly the gifted term ────────────
    assert after.period_end == _period_end(before) + dt.timedelta(days=365)

    # ── What must NOT change ────────────────────────────────────────────────
    # §30.3: "an active subscription always retains its original currency and
    # rail until renewal — no mid-cycle conversion, ever." The gift was bought
    # in USD through Stripe. Her subscription stays ₹ on Razorpay.
    assert after.region is BillingRegion.INDIA
    assert after.price is not None and after.price.currency is Currency.INR
    assert after.plan is before.plan
    assert after.status is before.status
    # The SAME row, extended. A replacement would break every reference to it
    # and would reset `created_at`, which §7.3's minute-pool anniversary reads.
    assert row_after["_id"] == row_before["_id"]
    assert row_after["created_at"] == row_before["created_at"]

    # §30.3: "gift credits are denominated in their purchase currency". The
    # gift keeps its USD; the subscription it extended keeps its INR. Both are
    # true at once, which is only representable because they are separate rows.
    assert redemption.gift_value == Money(9900, Currency.USD)


async def test_a_gift_to_a_new_user_activates_rather_than_converting(
    service: PaymentService,
) -> None:
    """§30.3's other branch — "valid → onboarding with a gift banner"."""
    gift = await service.purchase_gift(
        buyer_user_id=str(GIVER_ID),
        plan=PlanId.ANNUAL,
        region=BillingRegion.INTERNATIONAL,
        idempotency_key="idem-gift-new",
        now=NOW,
    )
    redemption = await service.redeem_gift(user_id=str(USER_ID), code=gift.code, now=NOW)
    view = await service.read(user_id=str(USER_ID), now=NOW)

    assert redemption.outcome is GiftRedemptionOutcome.ACTIVATED
    assert view.status is SubscriptionStatus.ACTIVE
    assert view.access is AccessLevel.FULL
    assert view.period_end == NOW + dt.timedelta(days=365)


async def test_a_gift_redeems_exactly_once(service: PaymentService, db) -> None:  # noqa: ANN001
    """The gift equivalent of the double webhook, and the same shape of loss."""
    await _subscribed(service, plan=PlanId.MONTHLY)
    gift = await service.purchase_gift(
        buyer_user_id=str(GIVER_ID),
        plan=PlanId.ANNUAL,
        region=BillingRegion.INDIA,
        idempotency_key="idem-gift-once",
        now=NOW,
    )
    first = await service.redeem_gift(user_id=str(USER_ID), code=gift.code, now=NOW)
    extended = await service.read(user_id=str(USER_ID), now=NOW)

    second = await service.redeem_gift(user_id=str(USER_ID), code=gift.code, now=NOW)
    after = await service.read(user_id=str(USER_ID), now=NOW)

    assert first.outcome is GiftRedemptionOutcome.CREDIT_CONVERTED
    assert second.outcome is GiftRedemptionOutcome.ALREADY_REDEEMED

    # ── What must NOT change ────────────────────────────────────────────────
    assert after.period_end == extended.period_end
    assert await db.subscriptions.count_documents({"user_id": USER_ID}) == 1


async def test_an_unknown_code_and_an_expired_code_answer_identically(
    service: PaymentService,
) -> None:
    """Two different truths, one message — deliberately.

    §30.3 gives expired, used and invalid the same warm error and support link,
    and that is also the only safe answer: a response that distinguished "this
    code expired" from "no such code" is an oracle for enumerating gift codes,
    and a gift code is a bearer instrument.
    """
    expired = await service.purchase_gift(
        buyer_user_id=str(GIVER_ID),
        plan=PlanId.ANNUAL,
        region=BillingRegion.INDIA,
        idempotency_key="idem-gift-expired",
        now=NOW - dt.timedelta(days=400),
    )
    stale = await service.redeem_gift(user_id=str(USER_ID), code=expired.code, now=NOW)
    unknown = await service.redeem_gift(user_id=str(USER_ID), code="SITARA-NOPE-NOPE", now=NOW)

    assert stale.outcome is GiftRedemptionOutcome.EXPIRED
    assert unknown.outcome is GiftRedemptionOutcome.INVALID
    # The OUTCOMES differ so the server can log the difference; the message the
    # user is shown does not, and that is what this asserts.
    assert stale.message_key == unknown.message_key


# ---------------------------------------------------------------------------
# The states that only exist because a rail is involved
# ---------------------------------------------------------------------------


async def test_a_pending_upi_purchase_grants_nothing_until_it_settles(
    service: PaymentService,
) -> None:
    """§30.3's 5-minute hold. `pending` is not access and is not an error."""
    rail = SimulatedRail()
    rail.arm(Fault.HOLD_PENDING)
    service = PaymentService(service._db, rail)  # noqa: SLF001

    handle = await service.start_purchase(
        user_id=str(USER_ID),
        plan=PlanId.MONTHLY,
        region=BillingRegion.INDIA,
        idempotency_key="idem-pending",
        now=NOW,
    )
    view = await service.read(user_id=str(USER_ID), now=NOW)

    assert handle.pending is True
    assert view.status is SubscriptionStatus.PENDING
    assert view.access is AccessLevel.NONE

    # It settles when the user approves in their UPI app.
    await service.handle_event(handle.authorisation_event(now=NOW), now=NOW)
    settled = await service.read(user_id=str(USER_ID), now=NOW)
    assert settled.status is SubscriptionStatus.ACTIVE
    assert settled.access is AccessLevel.FULL


async def test_a_failed_purchase_leaves_no_subscription_at_all(
    service: PaymentService, db  # noqa: ANN001
) -> None:
    """A declined first payment is not a lapsed subscriber. There is no row to
    put in grace, because nothing was ever granted."""
    rail = SimulatedRail()
    rail.arm(Fault.DECLINE, reason=PaymentFailureReason.INSUFFICIENT_FUNDS)
    service = PaymentService(service._db, rail)  # noqa: SLF001

    handle = await service.start_purchase(
        user_id=str(USER_ID),
        plan=PlanId.MONTHLY,
        region=BillingRegion.INDIA,
        idempotency_key="idem-declined",
        now=NOW,
    )
    view = await service.read(user_id=str(USER_ID), now=NOW)

    assert handle.failure_reason is PaymentFailureReason.INSUFFICIENT_FUNDS
    assert view.status is None
    assert view.access is AccessLevel.NONE
    assert await db.subscriptions.count_documents({"user_id": USER_ID, "status": "grace"}) == 0
