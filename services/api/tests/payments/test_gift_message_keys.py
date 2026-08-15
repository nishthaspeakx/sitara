"""Every gift message key the server SENDS must exist in every catalog (§2.4).

This test exists because the failure it catches had already shipped and nothing
saw it. `gifting.py` has sent `pay.gift.activated` and `pay.gift.converted`
since M11; the catalogs carried those two strings at `gift.activated` and
`gift.converted`. Parity kept all three locales consistently wrong, so the
i18n gate was green — and `packages/i18n`'s gate 2 does not scan the `pay`
namespace at all, so nothing checked that the key a screen would ask for
existed. No screen consumed them until S33 was built, which is the only reason
it never surfaced: a successful redemption would have rendered a raw dotted key
at the one moment a gift is meant to feel like a welcome.

The i18n lint's namespace list has been widened, which closes it from the
client side. This closes it from the side the constants actually live on — a
key renamed in `gifting.py` fails here, on the commit that renames it, without
anyone remembering to update a regex in another package.
"""

from __future__ import annotations

import pytest

from sitara_api.localisation import resolve
from sitara_api.payments import gifting

#: §2.4's launch locales. No English fallback exists, so "resolves in en" is
#: not evidence about the other two.
LOCALES = ("en", "hi", "hi-Latn")

#: Every user-facing key the gifting module can put in a response. Read off the
#: module's own constants rather than restated, so a rename moves both.
GIFT_MESSAGE_KEYS = (
    gifting.GIFT_UNREDEEMABLE_KEY,
    gifting.GIFT_ACTIVATED_KEY,
    gifting.GIFT_CONVERTED_KEY,
)


@pytest.mark.parametrize("key", GIFT_MESSAGE_KEYS)
@pytest.mark.parametrize("locale", LOCALES)
def test_every_gift_message_key_resolves(key: str, locale: str) -> None:
    assert resolve(key, locale).strip()


def test_every_outcome_carries_a_key_that_resolves() -> None:
    """The enum and the catalogs, checked against each other.

    `refusal()` maps three distinct outcomes onto ONE key deliberately — a
    response that told expired, used and unknown apart would be an oracle for
    enumerating bearer instruments. That is a property worth pinning here too:
    the point is that every outcome has SOME resolvable key, not that each has
    its own.
    """
    from sitara_schemas.payments import GIFT_REDEMPTION_OUTCOMES, GiftRedemptionOutcome

    for outcome in GIFT_REDEMPTION_OUTCOMES:
        if outcome in (
            GiftRedemptionOutcome.ACTIVATED,
            GiftRedemptionOutcome.CREDIT_CONVERTED,
        ):
            continue
        key = gifting.refusal(outcome).message_key
        for locale in LOCALES:
            assert resolve(key, locale).strip()
