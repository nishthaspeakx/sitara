"""Which rail the app holds (§30.3, §3.2's adapter discipline).

One function, and it makes no decision of its own: `routing.resolve()` names
the provider and this maps the name to a class. The mapping is exhaustive over
`PaymentProviderName`, so a rail added to the enum without an entry here fails
at boot rather than at the first purchase.

**There is no `if settings.prototype` in this file.** That shape — a fake
behind a flag — gives the service two code paths, and the one that will
eventually carry real money is the one that has never run. The simulator is
selected because its capability cell says IMPLEMENTED and the real rails' cells
say DECLARED; the day Razorpay's cell flips, `resolve()` returns it and this
function hands back a `RazorpayRail` with nothing else edited.
"""

from __future__ import annotations

import logging

from sitara_schemas.payments import BillingRegion

from sitara_api.payments.providers.base import PaymentProvider, PaymentProviderName
from sitara_api.payments.providers.razorpay import RazorpayRail
from sitara_api.payments.providers.routing import resolve
from sitara_api.payments.providers.simulator import SimulatedRail
from sitara_api.payments.providers.stripe import StripeRail

logger = logging.getLogger(__name__)

_RAILS: dict[PaymentProviderName, type] = {
    PaymentProviderName.SIMULATOR: SimulatedRail,
    PaymentProviderName.RAZORPAY: RazorpayRail,
    PaymentProviderName.STRIPE: StripeRail,
}


def build_rail(region: BillingRegion = BillingRegion.INDIA) -> PaymentProvider:
    """The rail for a region, per the capability matrix.

    Falls back to the SIMULATOR only when the matrix already selected it —
    which is not a fallback at all, but the answer. When `resolve()` returns
    nobody, the app still needs an object to hold; it gets the simulator, and
    `router.purchase` refuses the purchase separately by asking `resolve()`
    itself. The refusal lives at the door rather than in the object, so a
    region with no rail is a purchase that was never offered rather than one
    that failed halfway.
    """
    route = resolve(region)
    if route.provider is None:
        logger.warning(
            "no payment rail is IMPLEMENTED for %s (§30.3) — purchases in that region "
            "are refused at the door with PAY_RAIL_UNAVAILABLE",
            region.value,
        )
        return SimulatedRail()
    return _RAILS[route.provider]()
