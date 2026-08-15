"""Gift codes and what redeeming one does (§30.3, §10-20, §25/§27).

§30.3 gives S33 five outcomes and one of them is arithmetic rather than a
message:

    valid, no subscription   → activated
    valid, already subscribed → **credit conversion**
    expired / used / unknown  → warm error + support link

── "Credit conversion" means EXTEND, and the word matters ──────────────────

The giver bought a term. The receiver already has a term. §30.3 says the
redemption converts to credit rather than replacing, and the only honest
reading is that the two ADD: anything else destroys something one of the two
people paid for, silently, and neither of them finds out until the month the
receiver expected to still be subscribed.

**The extension is in DAYS, never in money.** §30.3 stacks three sentences on
this and they only reconcile one way:

  · "an active subscription always retains its original currency and rail until
    renewal — no mid-cycle conversion, ever"
  · "gift credits are denominated in their purchase currency"
  · and yet a USD gift must extend an INR subscription (§10-20's NRI case:
    "buy in USD, redeem in India")

A currency conversion is forbidden, the gift keeps its own currency, and the
subscription keeps its own — so the thing that crosses between them cannot be
money. It is time, which has no currency. `lifecycle.extend` therefore takes
`days`, and there is no exchange rate in this package to reach for.

── Why every failure answers the same way ──────────────────────────────────

A gift code is a bearer instrument: whoever has it can spend it. A response
that distinguished "expired" from "no such code" is an oracle for enumerating
them, and §30.3 gives all three the same warm error and support link anyway.
The OUTCOMES stay distinct so the server can log which happened; the
`message_key` is one value, and a test asserts that the two agree.
"""

from __future__ import annotations

import datetime as dt
import secrets
from dataclasses import dataclass

from sitara_schemas.payments import (
    BillingRegion,
    GiftRedemptionOutcome,
    PlanId,
)

from sitara_api.payments.money import Money

#: §30.3's warm error. ONE key for all three failures — see the header.
GIFT_UNREDEEMABLE_KEY = "pay.gift.unredeemable"
GIFT_ACTIVATED_KEY = "pay.gift.activated"
GIFT_CONVERTED_KEY = "pay.gift.converted"

#: How long a bought gift stays redeemable. §30.3 names an expired state and
#: no duration; a year matches the longest term sold, so a gift can never
#: expire before the thing it buys would have.
GIFT_VALIDITY_DAYS = 365

#: Unambiguous alphabet — no O/0, no I/1/L. A gift code gets read aloud down a
#: phone line and typed by someone who did not choose it, and a code that is
#: hard to transcribe turns into a support ticket about a code that "doesn't
#: work". Excluded characters are cheaper than the ticket.
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def mint_code() -> str:
    """`SITARA-XXXX-XXXX`.

    `secrets`, never `random`: this is a bearer instrument, and the module
    whose docs say "not suitable for security purposes" is not the one to mint
    it with. 8 characters over a 31-character alphabet is ~40 bits, which is
    not guessable at any rate a rate limiter permits.
    """
    body = "".join(secrets.choice(_ALPHABET) for _ in range(8))
    return f"SITARA-{body[:4]}-{body[4:]}"


@dataclass(frozen=True)
class Gift:
    """A purchased gift, before anyone has redeemed it."""

    code: str
    buyer_user_id: str
    plan: PlanId
    #: The region it was BOUGHT in, which fixes its currency and its rail. It
    #: has nothing to do with where it will be redeemed (§10-20's NRI case is
    #: precisely the two differing) and must never be copied onto the
    #: redeemer's subscription.
    region: BillingRegion
    value: Money
    term_days: int
    purchased_at: dt.datetime
    expires_at: dt.datetime
    redeemed_by_user_id: str | None = None
    redeemed_at: dt.datetime | None = None

    def redeemable_at(self, now: dt.datetime) -> GiftRedemptionOutcome | None:
        """None when it may be redeemed; the refusal otherwise."""
        if self.redeemed_by_user_id is not None:
            return GiftRedemptionOutcome.ALREADY_REDEEMED
        if now >= self.expires_at:
            return GiftRedemptionOutcome.EXPIRED
        return None


@dataclass(frozen=True)
class Redemption:
    """What happened, for S33 and for the log.

    `gift_value` is the gift's OWN money in the gift's OWN currency (§30.3:
    "gift credits are denominated in their purchase currency"). It is reported
    rather than applied — the subscription was extended in days, and this is
    what the receipt says the giver spent.
    """

    outcome: GiftRedemptionOutcome
    message_key: str
    gift_value: Money | None = None
    extended_to: dt.datetime | None = None

    @property
    def succeeded(self) -> bool:
        return self.outcome in (
            GiftRedemptionOutcome.ACTIVATED,
            GiftRedemptionOutcome.CREDIT_CONVERTED,
        )


def refusal(outcome: GiftRedemptionOutcome) -> Redemption:
    """Every failure, wearing one message. See the module header."""
    return Redemption(outcome=outcome, message_key=GIFT_UNREDEEMABLE_KEY)
