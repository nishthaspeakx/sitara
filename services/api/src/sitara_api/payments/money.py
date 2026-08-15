"""Money, and the price book (§30.3, §2.3, §22.1, §10-20).

Two rules, and the whole module is them.

**1. Money is an integer count of minor units.** Never a float, never a
Decimal-that-came-from-a-float. `0.1 + 0.2 != 0.3` is the oldest bug in
commercial software and it does not become acceptable because a simulator is
what moves the money — the arithmetic in this file is the arithmetic that will
run when Razorpay is wired, and a rounding error introduced here would be
introduced for real. ₹499 is `Money(49900, INR)`.

**2. Two currencies never meet.** §30.3 is unusually forceful about this: "an
active subscription always retains its original currency and rail until renewal
— no mid-cycle conversion, ever", "refunds always return through the original
rail in the original currency", "gift credits are denominated in their purchase
currency". A conversion is not a thing this system is allowed to do, so `Money`
raises on any operation between two currencies rather than carrying a rate
nobody may use. **There is deliberately no exchange rate anywhere in this
package** — not a constant, not a config key, not a provider call. The one
place §30.3 contemplates a conversion (a gift redeemed in another currency) is
handled by NOT converting: the gift keeps its own currency and grants TIME,
which has no currency at all.

── Where the prices come from ──────────────────────────────────────────────

§30.3 and §10-20 state all six, and they are the only prices in the codebase:

    India         monthly  ₹499      annual  ₹3,999   founding annual  ₹2,999
    International monthly  $12.99    annual  $99      founding annual  $79

── Tax, and the one thing that is NOT settled ──────────────────────────────

§29.2's S31 acceptance requires "price total incl. tax shown before payment
rail", so `PriceCard` requires a `totalWithTax` and every price here must be
able to produce one honestly.

§22.1 settles the international half outright: Stripe India bills the diaspora
as a **zero-rated export of services under LUT**, so tax is zero and the total
is the price. The India half it does not settle — it says Razorpay bills India
"GST-invoiced" and puts GST registration in W2 procurement, and no section of
the spec states a rate. So the displayed ₹ prices are declared TAX-INCLUSIVE
here, which is Indian consumer convention and satisfies §29.2 without inventing
a number. What is genuinely missing is the invoice SPLIT — the net-of-tax line
and the GST line a §22.1 invoice must carry — and that needs finance's rate
rather than a plausible 18%. It is recorded as the `payments.gst_invoice_rate`
release gate rather than guessed at here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self

from sitara_schemas.payments import BillingRegion, Currency, PlanId

#: Both currencies here divide by 100. Declared as data anyway, because the
#: assumption is wrong for about a dozen world currencies (JPY has no minor
#: unit; KWD has three digits) and a hardcoded `/ 100` is how the first
#: zero-decimal currency added to the price book becomes a hundredfold error.
MINOR_UNITS: dict[Currency, int] = {
    Currency.INR: 100,
    Currency.USD: 100,
}


class CurrencyMismatch(TypeError):
    """Two currencies met. §30.3 forbids the conversion that would resolve it."""


@dataclass(frozen=True, order=False)
class Money:
    """An exact amount in one currency.

    Frozen, so an amount cannot be adjusted in place by something holding a
    reference to it — every operation returns a new value, and a refund that
    mutated the payment it was reversing would be very hard to see.
    """

    minor: int
    currency: Currency

    def __post_init__(self) -> None:
        if not isinstance(self.minor, int) or isinstance(self.minor, bool):
            raise TypeError(
                f"Money takes an integer count of minor units, got {type(self.minor).__name__}. "
                "A float here is the rounding error that reaches a bank statement."
            )

    def _same(self, other: Money) -> None:
        if self.currency is not other.currency:
            raise CurrencyMismatch(
                f"{self.currency} and {other.currency} cannot be combined. §30.3: an "
                "active subscription retains its original currency, refunds return in "
                "the original currency, and gift credits stay denominated in theirs — "
                "so there is no exchange rate in this package to reach for."
            )

    def __add__(self, other: Money) -> Money:
        self._same(other)
        return Money(self.minor + other.minor, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._same(other)
        return Money(self.minor - other.minor, self.currency)

    def __lt__(self, other: Money) -> bool:
        self._same(other)
        return self.minor < other.minor

    @property
    def is_zero(self) -> bool:
        return self.minor == 0

    def negated(self) -> Self:
        """A refund is the charge with its sign flipped, in the same currency."""
        return type(self)(-self.minor, self.currency)

    def as_wire(self) -> dict[str, object]:
        """What crosses to the client.

        MINOR UNITS, never a formatted string and never a float. §2.3 puts
        Indian digit grouping on INR and Western grouping on USD, and CC-013
        puts Latin numerals on every locale — all three are locale-aware
        FORMATTING decisions and they belong on the client beside `Intl`, which
        is where `apps/web/src/lib/money.ts` makes them. A server that sent
        "₹499" would have picked a grouping for a locale it was only guessing
        at, and a server that sent 499.0 would have picked a rounding.
        """
        return {"minor": self.minor, "currency": self.currency.value}


@dataclass(frozen=True)
class Price:
    """One cell of the price book."""

    amount: Money
    #: §22.1. `inclusive` means `amount` IS the total a card is charged;
    #: `zero_rated` means there is no tax to add. Both make §29.2's
    #: "total incl. tax" equal to `amount` — by two different routes, and the
    #: distinction matters on the invoice even though it never shows on S31.
    tax_treatment: str
    #: Days of access one purchase buys. A term, not a currency — which is what
    #: makes a USD gift extendable onto an INR subscription without a rate.
    term_days: int

    @property
    def total_with_tax(self) -> Money:
        """§29.2's acceptance line. See `tax_treatment`."""
        return self.amount


#: 365 for the annual term rather than a calendar year: §30.3 has to be able to
#: ADD terms (a gift onto an existing subscription) and calendar arithmetic
#: does not associate — twelve month-additions from 31 January and one
#: year-addition land on different days. A fixed term is the only kind that can
#: be added twice and come out the same.
MONTHLY_TERM_DAYS = 30
ANNUAL_TERM_DAYS = 365

#: §30.3 + §10-20. Every price in the product, and there are no others.
PRICES: dict[tuple[BillingRegion, PlanId], Price] = {
    (BillingRegion.INDIA, PlanId.MONTHLY): Price(
        Money(49_900, Currency.INR), "inclusive", MONTHLY_TERM_DAYS
    ),
    (BillingRegion.INDIA, PlanId.ANNUAL): Price(
        Money(399_900, Currency.INR), "inclusive", ANNUAL_TERM_DAYS
    ),
    (BillingRegion.INTERNATIONAL, PlanId.MONTHLY): Price(
        Money(1_299, Currency.USD), "zero_rated", MONTHLY_TERM_DAYS
    ),
    (BillingRegion.INTERNATIONAL, PlanId.ANNUAL): Price(
        Money(9_900, Currency.USD), "zero_rated", ANNUAL_TERM_DAYS
    ),
}

#: §10-20's "founding offer $79/₹2,999 first year". Annual only, first year
#: only, and §30.3 states its own limit: "promotional/founding pricing does NOT
#: transfer automatically across regions (stated at switch)". `founding_price`
#: is the only reader, and the migration path deliberately does not call it.
FOUNDING_ANNUAL: dict[BillingRegion, Price] = {
    BillingRegion.INDIA: Price(Money(299_900, Currency.INR), "inclusive", ANNUAL_TERM_DAYS),
    BillingRegion.INTERNATIONAL: Price(Money(7_900, Currency.USD), "zero_rated", ANNUAL_TERM_DAYS),
}

#: §10-20's trial. Priced at zero in the region's own currency so that a trial
#: row is shaped like every other row and nothing downstream needs a null-price
#: branch — the branch that would eventually be taken by a real plan.
TRIAL_TERM_DAYS = 7


class NoSuchPrice(KeyError):
    """§2.4's rule pointed at money: an unpriced combination DECLINES.

    There is no default, no nearest-region fallback and no "use the monthly
    price × 12". A combination this book does not name is one nobody has
    decided the price of, and charging a guess is worse than declining.
    """


def price_for(region: BillingRegion, plan: PlanId, *, founding: bool = False) -> Price:
    """The price of one plan in one region, or a refusal."""
    if plan is PlanId.TRIAL:
        return Price(Money(0, currency_for(region)), "zero_rated", TRIAL_TERM_DAYS)
    if founding:
        if plan is not PlanId.ANNUAL:
            raise NoSuchPrice(
                f"§10-20's founding offer is a FIRST-YEAR price and exists for the "
                f"annual plan only; there is no founding {plan.value} price to charge."
            )
        return FOUNDING_ANNUAL[region]
    try:
        return PRICES[(region, plan)]
    except KeyError:
        raise NoSuchPrice(
            f"no declared price for {plan.value} in {region.value} (§30.3 names six "
            "prices and this is not one of them)"
        ) from None


def currency_for(region: BillingRegion) -> Currency:
    """§22.1's rail-to-currency binding.

    A function rather than a dict comprehension over `PRICES` so that the
    binding survives a region whose prices have not been declared yet — which
    is the state the international AED case §30.3 mentions is actually in.
    """
    return {
        BillingRegion.INDIA: Currency.INR,
        BillingRegion.INTERNATIONAL: Currency.USD,
    }[region]
