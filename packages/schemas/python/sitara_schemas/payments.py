"""GENERATED FILE — do not edit. Source: packages/schemas/src/*.json (run scripts/generate.py).

SPEC §30.3 / §22.13 / §22.1 — the vocabulary of a subscription.

`sitara_api.payments` writes these onto `subscriptions` and `payments`
rows; S30, S31 and S34 render them. Declared here in the SAME milestone
that builds both sides, rather than after they had already disagreed —
which is what happened to the confidence states, the presence states,
the memory types and the voice vocabulary in turn.

The RULES over these states — which grant access, which are terminal,
what §22.13's clock does to them — belong to `payments.lifecycle`,
exactly as §32.4's consent and decay rules stay in `memory.taxonomy`.
This file is the closed set of IDs and nothing else.
"""

from enum import StrEnum

__all__ = [
    "ANNUAL_REFUND_WINDOW_DAYS",
    "BILLING_REGIONS",
    "BillingRegion",
    "CURRENCIES",
    "Currency",
    "DUNNING_NUDGE_DAYS",
    "GIFT_REDEMPTION_OUTCOMES",
    "GRACE_PERIOD_DAYS",
    "GiftRedemptionOutcome",
    "PAYMENT_FAILURE_REASONS",
    "PAYMENT_STATES",
    "PLAN_IDS",
    "PaymentFailureReason",
    "PaymentState",
    "PlanId",
    "READ_ONLY_PERIOD_DAYS",
    "SUBSCRIPTION_STATUSES",
    "SubscriptionStatus",
    "TRIAL_DAYS",
    "UPI_PENDING_HOLD_MINUTES",
    "WIN_BACK_DAY",
]


class PlanId(StrEnum):
    """What a person may BUY, plus the trial that precedes it. §30.3 names monthly and annual in both regions and §10-20 makes the trial 7 days. Deliberately NOT the same set as `voice.entitlements.CallPlan`, which is a POOL LOOKUP and carries `premium` (§7.3's unlimited fair-use tier, which nothing sells) and `none` (an account with no subscription at all, which is a state rather than a plan). The two are kept in step by a test rather than by being one enum: every purchasable plan must resolve to a minute pool, and `CallPlan` must keep the two members this set has no business naming."""

    TRIAL = "trial"
    MONTHLY = "monthly"
    ANNUAL = "annual"


PLAN_IDS: tuple[PlanId, ...] = (
    PlanId.TRIAL,
    PlanId.MONTHLY,
    PlanId.ANNUAL,
)


class BillingRegion(StrEnum):
    """§30.3's two rails, named for the BILLING relationship rather than for geography — which is the distinction the migration policy turns on. A subscriber who moves to Dubai stays `india` until renewal because their subscription is billed in ₹ through Razorpay; where they are standing is §30.2's Travel Mode and has nothing to do with this field. §22.1: the Indian entity bills India in INR with GST, and bills the diaspora through Stripe India as a zero-rated export of services under LUT."""

    INDIA = "india"
    INTERNATIONAL = "international"


BILLING_REGIONS: tuple[BillingRegion, ...] = (
    BillingRegion.INDIA,
    BillingRegion.INTERNATIONAL,
)


class Currency(StrEnum):
    """The currencies the price book actually declares. §22.1 says Stripe bills 'USD/GBP/etc.' and §30.3's worked case offers a departing subscriber 'USD/AED-equivalent' — neither is a price this milestone can state, so neither is a member. A currency with no declared price is a currency something would eventually have to convert into, and §30.3 forbids conversion outright."""

    INR = "INR"
    USD = "USD"


CURRENCIES: tuple[Currency, ...] = (
    Currency.INR,
    Currency.USD,
)


class SubscriptionStatus(StrEnum):
    """§22.13's ladder, as states rather than as flags. The two that carry the whole section are `grace` and `read_only`: both are FAILED renewals, and the difference between them is exactly what a user may still do — grace keeps everything and shows a banner, read-only keeps her memories and stops new guidance. Collapsing them into one 'past due' would erase §22.13's central promise, which is that nothing is taken away at the moment the money fails. `cancelled` GRANTS ACCESS: §30.3 says 'access till period end stated', so the subscription is over and the entitlement is not, and modelling that as a flag on `active` put the same fact in two fields."""

    PENDING = "pending"
    TRIALING = "trialing"
    ACTIVE = "active"
    GRACE = "grace"
    READ_ONLY = "read_only"
    CANCELLED = "cancelled"
    DOWNGRADED = "downgraded"
    EXPIRED = "expired"


SUBSCRIPTION_STATUSES: tuple[SubscriptionStatus, ...] = (
    SubscriptionStatus.PENDING,
    SubscriptionStatus.TRIALING,
    SubscriptionStatus.ACTIVE,
    SubscriptionStatus.GRACE,
    SubscriptionStatus.READ_ONLY,
    SubscriptionStatus.CANCELLED,
    SubscriptionStatus.DOWNGRADED,
    SubscriptionStatus.EXPIRED,
)


class PaymentState(StrEnum):
    """S34's three states plus the one a receipt row needs afterwards. `pending` is §30.3's UPI wait and is emphatically NOT an error — it borrows no error colour on S34 and no error colour in `ReceiptRow`, which had this right before there was a payments module behind it."""

    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"


PAYMENT_STATES: tuple[PaymentState, ...] = (
    PaymentState.PENDING,
    PaymentState.SUCCEEDED,
    PaymentState.FAILED,
    PaymentState.REFUNDED,
)


class PaymentFailureReason(StrEnum):
    """§30.3: 'mapped reasons in plain language: insufficient funds / mandate declined / bank timeout'. The mapping happens in the ADAPTER, so a vendor's own failure string never reaches a screen — §2.4 would render it in the wrong language even if §13 permitted it, which it does not. `unknown` is a real member and not a gap: a rail that returns something unmapped must still produce a screen, and the honest screen says the payment did not go through without inventing a cause."""

    INSUFFICIENT_FUNDS = "insufficient_funds"
    MANDATE_DECLINED = "mandate_declined"
    BANK_TIMEOUT = "bank_timeout"
    INSTRUMENT_EXPIRED = "instrument_expired"
    UNKNOWN = "unknown"


PAYMENT_FAILURE_REASONS: tuple[PaymentFailureReason, ...] = (
    PaymentFailureReason.INSUFFICIENT_FUNDS,
    PaymentFailureReason.MANDATE_DECLINED,
    PaymentFailureReason.BANK_TIMEOUT,
    PaymentFailureReason.INSTRUMENT_EXPIRED,
    PaymentFailureReason.UNKNOWN,
)


class GiftRedemptionOutcome(StrEnum):
    """§30.3's S33 branches, as an enum because the middle one is a MONEY MOVEMENT and not a message: 'already-subscribed → credit conversion'. A redemption that found an existing subscriber must EXTEND it — the giver bought time and the receiver already had time, so the two add. Replacing would silently destroy whatever the receiver had already paid for, which is the one outcome nobody would notice until the month they expected to still be subscribed."""

    ACTIVATED = "activated"
    CREDIT_CONVERTED = "credit_converted"
    EXPIRED = "expired"
    ALREADY_REDEEMED = "already_redeemed"
    INVALID = "invalid"


GIFT_REDEMPTION_OUTCOMES: tuple[GiftRedemptionOutcome, ...] = (
    GiftRedemptionOutcome.ACTIVATED,
    GiftRedemptionOutcome.CREDIT_CONVERTED,
    GiftRedemptionOutcome.EXPIRED,
    GiftRedemptionOutcome.ALREADY_REDEEMED,
    GiftRedemptionOutcome.INVALID,
)


#: §22.13 — 'a 7-day grace with in-locale WhatsApp/push nudges'. Access is UNCHANGED throughout it.
GRACE_PERIOD_DAYS = 7

#: §22.13 — 'then a 21-day read-only "your memories are safe" state before downgrade'.
READ_ONLY_PERIOD_DAYS = 21

#: §22.13 — 'nudges (day 0, 2, 5)', counted from the failed renewal. Three, inside a seven-day grace, and no fourth: §29.2 forbids the escalating drumbeat that the fourth would be.
DUNNING_NUDGE_DAYS = (0, 2, 5)

#: §10-20 — 'trial 7 days full-featured'.
TRIAL_DAYS = 7

#: §22.16 / §30.3 — '7-day no-questions on annual plans'. Monthly is deliberately absent from this constant: the spec grants the window to annual, and a helpful extension to monthly would be a policy decision made in a constants file.
ANNUAL_REFUND_WINDOW_DAYS = 7

#: §30.3 — the pending screen's hold: 'UPI waiting: 5-min hold screen with "approve in your UPI app"'. After it the purchase is abandoned, not failed: nothing was taken.
UPI_PENDING_HOLD_MINUTES = 5

#: §30.3 — 'single email/WhatsApp at +30d (Class M, consented) with nothing manipulative'. SINGLE. The number is here so the notification job and the screen copy cannot disagree about when, and the word 'single' is enforced where the job is written.
WIN_BACK_DAY = 30
