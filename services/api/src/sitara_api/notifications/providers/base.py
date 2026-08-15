"""The one notification-channel interface (§23.3, §23.6, §6.3, §13).

This is `payments/providers/base.py` and `voice/providers/base.py` applied to
delivery, and it keeps their two rules for their two reasons:

1. **Adapters return NORMALISED outcomes, never vendor responses.** A push
   service answers with an HTTP status, an SMTP server with a three-digit reply
   code, a WhatsApp BSP with a JSON error body. §23.6 makes a decision from
   those — a 410 kills a subscription immediately, a timeout counts one of
   three — and the decision is made HERE, once, so that no adapter's
   vocabulary reaches the store, a log or §23.8's dashboards.
2. **Adapters raise `ChannelUnavailable`, never an upstream body.** §13 keeps
   vendor payloads out of logs and §2.4 would render one in the wrong language
   even where §13 permitted it.

A third rule belongs to notifications alone:

3. **No method here can send to an address the caller supplied.** `Delivery`
   carries a `recipient` that the SERVICE resolved from the user's own row —
   never a string from a request body. A notification API that accepted a
   destination is an open relay with our sender reputation attached, and it is
   the shape a "just send this to my other email" feature request produces.

── What is implemented, and what is declared ───────────────────────────────

`WebPushChannel` and `SmtpChannel` are real: they speak the actual protocols,
against a real push service and a real SMTP host. `WhatsAppChannel` is
DECLARED — every method raises, `routing.CAPABILITIES` keeps it out of the
product, and `notifications.whatsapp_rail` is the release gate that names it.
That is the same treatment §30.3's two payment rails have, chosen for the same
reason: what is missing is mostly not code (a Meta Business account, a verified
sender, template categories approved per §23.3's utility-vs-marketing split),
and writing it as UNSUPPORTED would say something false about the product while
writing it as IMPLEMENTED would say something false about the code.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from sitara_schemas.notifications import (
    DeliveryFailure,
    MessageClass,
    NotificationChannel,
)


class ChannelProviderName(StrEnum):
    """The adapters, as far as this milestone implements them.

    Named after the PROTOCOL rather than the vendor wherever the protocol is
    the thing we depend on. `web_push_vapid` is a W3C/IETF standard and any
    conforming push service serves it — which is precisely why §6.2 chose it
    and why it needs no account; `smtp` is likewise a protocol and the host
    behind it is configuration. `whatsapp_cloud` is named for a vendor because
    it IS one: there is no second implementation of a WhatsApp BSP.
    """

    #: RFC 8291 + RFC 8292 over the browser's own Push API. IMPLEMENTED.
    WEB_PUSH_VAPID = "web_push_vapid"
    #: Ordinary SMTP. Mailpit locally, SES in production (§23.3). IMPLEMENTED.
    SMTP = "smtp"
    #: §23.3's Meta-compliant BSP path. DECLARED — no account, no adapter.
    WHATSAPP_CLOUD = "whatsapp_cloud"


class ChannelUnavailable(RuntimeError):
    """The channel could not answer. Maps to §34.4's `SYS_UNAVAILABLE`.

    Deliberately not carrying the upstream body — see the module header.
    """


class ChannelNotImplemented(ChannelUnavailable):
    """This channel is DECLARED and has no adapter behind it.

    A subclass, so every caller's existing `except ChannelUnavailable` already
    handles it: a channel that is not built and a channel that is down are the
    same thing to the §23.3 ladder, and they are different things to
    `/shipcheck`, which is where the distinction is read.
    """


@dataclass(frozen=True)
class Recipient:
    """Where one channel may reach this user.

    Resolved by the service from the user's own record, never from a request.
    Every field is optional because the honest answer for most users on most
    channels is "nowhere yet" — no push subscription, no WhatsApp opt-in — and
    §23.3's ladder is built on exactly that absence.
    """

    #: The browser's own subscription. Opaque here; `webpush.py` reads it.
    push_subscription: PushSubscription | None = None
    email: str | None = None
    #: E.164. Present for every account (§37.3 makes sign-up phone-first) and
    #: still not sufficient — §23.3 requires a recorded WhatsApp opt-in too.
    phone_e164: str | None = None
    whatsapp_opted_in: bool = False

    def reachable_on(self, channel: NotificationChannel) -> bool:
        match channel:
            case NotificationChannel.PUSH:
                return self.push_subscription is not None
            case NotificationChannel.EMAIL:
                return bool(self.email)
            case NotificationChannel.WHATSAPP:
                # Both halves. A phone number without §23.3's recorded opt-in
                # is a number Meta's policy forbids us messaging, and having
                # it is exactly what makes the mistake easy.
                return bool(self.phone_e164) and self.whatsapp_opted_in
        return False


@dataclass(frozen=True)
class PushSubscription:
    """A browser's own Push API subscription (§6.2), as the browser gives it.

    Three fields and no more: the endpoint the push service assigned, and the
    two keys RFC 8291 encrypts to. There is no vendor id, no app id and no
    account here, because web push has none — which is the property that let
    §6.2 choose it and lets this prototype implement it in full.
    """

    endpoint: str
    #: base64url, unpadded — the UA's P-256 public key (65 bytes uncompressed).
    p256dh: str
    #: base64url, unpadded — the UA's 16-byte auth secret.
    auth: str


@dataclass(frozen=True)
class Delivery:
    """One rendered message, on its way to one channel.

    `body` is already localised. §2.4 puts every string in the catalogs and
    this interface is downstream of that — an adapter that took a message KEY
    would be an adapter that could resolve it, and there would then be two
    renderers disagreeing about which locale a person reads in.
    """

    message_id: str
    message_class: MessageClass
    channel: NotificationChannel
    recipient: Recipient
    locale: str
    title: str
    body: str
    #: §24.1: "every push carries its deep link". A route, never an origin —
    #: the client joins it to its own.
    deep_link: str
    #: §23.4. The adapter passes it to the channel where the channel has a
    #: concept of one (web push's TTL header); the expiry SWEEP is what
    #: enforces it for the channels that do not.
    expires_at: dt.datetime
    #: §23.4's collapse key, where the channel can collapse for us.
    collapse_key: str | None = None
    #: §23.3 — List-Unsubscribe, Class M only. Read from `classes.policy`, so
    #: an adapter never decides it.
    unsubscribe_url: str | None = None


@dataclass(frozen=True)
class DeliveryOutcome:
    """What the channel did with it. NORMALISED — see rule 1.

    `provider_message_id` is §23.7's "provider ids" and is what makes a
    delivery traceable back to the thing that carried it without storing the
    thing that carried it.
    """

    accepted: bool
    provider: ChannelProviderName
    provider_message_id: str | None = None
    failure: DeliveryFailure | None = None

    def __post_init__(self) -> None:
        if self.accepted == (self.failure is not None):
            raise ValueError(
                "a DeliveryOutcome is accepted XOR failed — an outcome that is "
                "both would let §23.6's dead-token counter and §23.8's delivery "
                "rate disagree about the same send"
            )


class NotificationChannelAdapter(Protocol):
    """Every channel implements exactly this.

    One method. Notably ABSENT: anything that reads delivery state back from
    the channel. §23.7 makes the `notifications` document the single source of
    truth for a message's status, and a channel that also owned it would make
    "did this arrive" a question with two answers — the same reason
    `PaymentProvider` has no method that reads a subscription back from a rail.
    """

    name: ChannelProviderName
    channel: NotificationChannel

    async def send(self, delivery: Delivery) -> DeliveryOutcome:
        """Hand one message to the channel. Raises `ChannelUnavailable` only
        when the channel itself could not be reached at all; a channel that
        answered with a refusal returns a failed outcome instead, because
        §23.6 counts those two differently."""
        ...
