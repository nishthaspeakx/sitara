"""Which rail may serve which region (§30.3, §22.1, §3.2's adapter discipline).

This is `voice/providers/routing.py` for money, and it exists for the same
reason in a sharper form: **a payment rail that silently falls back is a rail
that charged the wrong entity in the wrong currency through the wrong tax
treatment.** §22.1 makes India INR-with-GST through Razorpay and the diaspora
USD-zero-rated-under-LUT through Stripe India — those are different legal
postures, not different endpoints, and a fallback between them is a compliance
event rather than a degraded experience.

So, exactly as with voice: the lookup can return NOTHING, and nothing is a
designed state.

    resolve(BillingRegion.INDIA)  -> Route(provider=None, ...)   in production
    resolve(BillingRegion.INDIA)  -> Route(provider=SIMULATOR)   in a prototype

There is deliberately no fallback parameter, no `or SIMULATOR` and no default
argument anywhere in this module. The way the ruling gets reversed by accident
is someone adding a sensible-looking default to a function that had none.

── Why the simulator is a CELL and not a branch ────────────────────────────

The obvious prototype is `if settings.prototype: use_the_fake()`. That shape
puts the fake behind an `if` in the service, which means the service has two
code paths, which means the path that will carry real money is the one that has
never run. Here the simulator is a provider like any other, selected by the
same matrix, through the same `resolve()`, returning the same normalised types.
When Razorpay lands, the change is one cell — `DECLARED` → `IMPLEMENTED` —
plus an adapter class. Not a refactor, not a new branch, and nothing at all in
`payments/service.py`, which has never known which rail answered.

That is the same one-cell promise `voice/providers/routing.py` makes about
Sarvam's streaming arm, and it is kept the same way: the release gate reads
THIS TABLE, so the day a cell flips the gate closes itself.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

from sitara_schemas.payments import BillingRegion

from sitara_api.payments.providers.base import PaymentProviderName

logger = logging.getLogger(__name__)


class Support(StrEnum):
    """What we can honestly say about a (provider, region) cell."""

    #: An adapter exists and has been exercised end to end.
    IMPLEMENTED = "implemented"
    #: §30.3 names this rail for this region and no adapter is written. It
    #: cannot serve traffic. This is the state a release gate should watch.
    DECLARED = "declared"
    #: This rail does not serve this region and never will. Not a gap.
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class Route:
    """The answer, including when the answer is "no one".

    `reason_key` is a message KEY and not a sentence — §2.4 puts every
    user-facing string in the catalogs, and this reason reaches S31.
    """

    provider: PaymentProviderName | None
    support: Support
    reason_key: str | None = None

    @property
    def available(self) -> bool:
        return self.provider is not None


#: (provider, region) → Support.
#:
#: **The two DECLARED rows are the whole point of this milestone's honesty.**
#: §30.3 specifies Razorpay for India and Stripe for international; neither has
#: an account, a key or an adapter, and writing them as UNSUPPORTED would say
#: something false about the product while writing them as IMPLEMENTED would
#: say something false about the code. DECLARED is the third answer, and it is
#: what `payments.live_rails` reads.
CAPABILITIES: dict[tuple[PaymentProviderName, BillingRegion], Support] = {
    # §22.1: Razorpay bills India in INR, GST-invoiced. UPI Autopay e-mandates
    # and tokenized cards per §22.13. No adapter — see `razorpay.py`.
    (PaymentProviderName.RAZORPAY, BillingRegion.INDIA): Support.DECLARED,
    # Razorpay does not settle the diaspora in this architecture; §22.1 routes
    # them to Stripe India under LUT. Not a gap we would ever close.
    (PaymentProviderName.RAZORPAY, BillingRegion.INTERNATIONAL): Support.UNSUPPORTED,
    # §22.1: Stripe India, zero-rated export of services. SCA-ready per §30.3.
    (PaymentProviderName.STRIPE, BillingRegion.INTERNATIONAL): Support.DECLARED,
    # §22.1 puts India on Razorpay for GST invoicing. Stripe billing an Indian
    # consumer would be the wrong tax posture, not merely the wrong choice.
    (PaymentProviderName.STRIPE, BillingRegion.INDIA): Support.UNSUPPORTED,
    # The prototype's rail. Both regions, because §30.3's migration policy is a
    # rule ABOUT the two regions and cannot be demonstrated from inside one.
    (PaymentProviderName.SIMULATOR, BillingRegion.INDIA): Support.IMPLEMENTED,
    (PaymentProviderName.SIMULATOR, BillingRegion.INTERNATIONAL): Support.IMPLEMENTED,
}

#: Preference order. The real rails are consulted FIRST and — being DECLARED
#: rather than IMPLEMENTED — are never selected, which is what keeps this list
#: honest rather than decorative: the day Razorpay's cell flips, it wins
#: without anyone editing this tuple.
PREFERENCE: tuple[PaymentProviderName, ...] = (
    PaymentProviderName.RAZORPAY,
    PaymentProviderName.STRIPE,
    PaymentProviderName.SIMULATOR,
)


def resolve(region: BillingRegion) -> Route:
    """Which rail may take money for this region.

    Returns a Route with `provider=None` when none may — which is what a
    production deployment gets today for both regions if the simulator is not
    permitted, and is the correct answer rather than an error.
    """
    best = Support.UNSUPPORTED
    for provider in PREFERENCE:
        support = CAPABILITIES.get((provider, region), Support.UNSUPPORTED)
        if support is Support.IMPLEMENTED:
            return Route(provider=provider, support=support)
        if support is Support.DECLARED:
            best = Support.DECLARED

    if best is Support.DECLARED:
        return Route(
            provider=None,
            support=Support.DECLARED,
            reason_key="errors.pay.rail_pending",
        )
    return Route(
        provider=None,
        support=Support.UNSUPPORTED,
        reason_key="errors.pay.rail_unavailable",
    )


def purchases_available_in(region: BillingRegion) -> bool:
    """S31's affordance gate.

    One function so that "we cannot take money in this region" is one fact with
    one implementation, rather than a condition repeated across the paywall,
    the router and the renewal job — the three places it would drift between.
    """
    return resolve(region).available


def unimplemented_rails() -> tuple[tuple[PaymentProviderName, BillingRegion], ...]:
    """Every DECLARED cell, for the release gate to name.

    Read rather than listed, so the gate cannot go stale in either direction:
    it closes itself when the last cell flips, and it re-opens if someone adds
    a region before its rail.
    """
    return tuple(
        sorted(
            (
                (provider, region)
                for (provider, region), support in CAPABILITIES.items()
                if support is Support.DECLARED
            ),
            key=lambda cell: (cell[0].value, cell[1].value),
        )
    )


def is_simulated(provider: PaymentProviderName | None) -> bool:
    """Whether the answer came from the rail that moves no money.

    Read by S30 and by `PaymentService` so that a receipt from the simulator is
    LABELLED as one. A prototype whose receipts were indistinguishable from
    real ones is a prototype somebody eventually shows to a customer.
    """
    return provider is PaymentProviderName.SIMULATOR
