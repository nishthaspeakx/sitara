"""§23.3's WhatsApp rung. DECLARED, not implemented — the release gate names it.

This file holds a place and every method raises. It is `razorpay.py` and
`stripe.py` for messaging, and it gets that treatment for the same reason:
**what is missing here is mostly not code.**

── What closing this actually needs ────────────────────────────────────────

**A Meta Business account with a verified business**, an approved WhatsApp
Business Account, and a phone number registered to it. None of these is
something a developer can create in an afternoon; verification is a documents
review against a real legal entity, and §22.1 already puts the Indian entity's
paperwork in W2 procurement.

**A BSP relationship or Cloud API access**, with the permanent access token
and app secret in AWS Secrets Manager (§13, never an env file), and the webhook
verify-token for the delivery-receipt callback that would move a message from
`sent` to `delivered` (§23.7).

**Message templates, submitted and approved per locale, in two CATEGORIES.**
This is the part specific to §23.3 and it is the part that cannot be rushed:

    "utility vs marketing template categories mapped to classes D/T vs M
     (billing differs — utility conversation pricing budgeted at ₹0.35/msg
     planning rate, marketing ₹0.85)"

Every Class-D and Class-T message needs an approved UTILITY template and every
Class-M message a MARKETING one, in `en`, `hi` and `hi-Latn` — §2.4 admits no
English fallback, so a locale whose template was rejected is a locale where
this channel does not exist rather than one that falls back. Meta reviews each
one, rejects for reasons that are not always legible, and re-review takes days.
The §14 named native reviewer has to sign the copy before it is submitted, the
same gate the safety corpora sit behind.

**The 24-hour customer-service window**, which §23.3 uses for reply-driven
flows ("user replies to a brief → session messages are free-form until window
closes"). That is a stateful thing to get right and has no analogue in the
other two channels.

**Opt-in and STOP.** §23.3 requires Meta-compliant explicit opt-in captured at
onboarding step 21 and recorded in `consents`; §23.6 requires a user-initiated
"STOP" honoured within the provider SLA and mirrored into `consents` and the
preference centre. The opt-in half is BUILT — `Recipient.reachable_on` refuses
a phone number without a recorded opt-in, and the preference matrix has its
column — because those are our side of the contract and they are what stop a
future adapter from being wired to a channel with no consent behind it.

── The CODE is one cell plus an adapter ────────────────────────────────────

`routing.CAPABILITIES`'s `(WHATSAPP_CLOUD, WHATSAPP)` cell goes DECLARED →
IMPLEMENTED, and a class here implements `send`. Nothing in
`notifications/service.py` changes: it has never known which channel answered.
`test_landing_whatsapp_is_ONE_cell` asserts that literally.

── Why the methods raise rather than returning a failure ───────────────────

Two guards, deliberately, because they fail differently. The matrix keeps this
channel out of the ladder; the raise keeps a future caller that constructs one
directly — which is how "a quick test against the real thing" gets written —
from silently doing nothing and reporting success. A `DeliveryOutcome(accepted=
False)` here would be indistinguishable from a real send that failed, and would
therefore be counted by §23.8 as a delivery problem rather than as a channel
that does not exist.
"""

from __future__ import annotations

from sitara_schemas.notifications import NotificationChannel

from sitara_api.notifications.providers.base import (
    ChannelNotImplemented,
    ChannelProviderName,
    Delivery,
    DeliveryOutcome,
)

#: §23.3's planning rates, recorded so the cost model and this file cannot
#: disagree about which category a class maps to. Not used by any code path —
#: there is no code path — and kept because the mapping is the decision that
#: makes the templates submittable, and it is stated in exactly one sentence
#: of the spec.
TEMPLATE_CATEGORY_BY_CLASS = {
    "transactional": "utility",
    "daily_loop": "utility",
    "contextual": "utility",
    "marketing": "marketing",
}


class WhatsAppChannel:
    """§23.3's WhatsApp rung. Every method raises — see the module header."""

    name = ChannelProviderName.WHATSAPP_CLOUD
    channel = NotificationChannel.WHATSAPP

    def __init__(self) -> None:
        raise ChannelNotImplemented(
            "WhatsApp is DECLARED and has no adapter (§23.3). It needs a "
            "verified Meta Business account, Cloud API credentials in Secrets "
            "Manager, and utility + marketing templates approved per locale — "
            "see `notifications.whatsapp_rail` in `release_gates.py`. The "
            "constructor raises rather than the send method because a channel "
            "that can be built is a channel something will eventually build."
        )

    async def send(self, delivery: Delivery) -> DeliveryOutcome:
        raise ChannelNotImplemented("WhatsApp is DECLARED and has no adapter (§23.3)")
