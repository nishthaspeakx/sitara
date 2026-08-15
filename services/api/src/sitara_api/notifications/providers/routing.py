"""Which adapter may serve which channel (§23.3, §3.2's adapter discipline).

This is `payments/providers/routing.py` and `voice/providers/routing.py` for
delivery, and it keeps their central rule: **the lookup can return NOTHING, and
nothing is a designed state.**

    resolve(NotificationChannel.WHATSAPP) -> Route(provider=None, DECLARED)
    resolve(NotificationChannel.PUSH)     -> Route(provider=WEB_PUSH_VAPID)

There is deliberately no fallback parameter, no `or SMTP` and no default
argument anywhere in this module. A silent fallback here is not the compliance
event a payment rail's would be, but it is worse than it looks: §23.3's ladder
is a DESIGNED fallback with a dedupe key behind it, and a second, accidental
fallback inside `resolve` would bypass that key — which is how the same message
goes out on two channels, which §23.9 makes release-blocking.

── Why WhatsApp is a cell and not a comment ────────────────────────────────

`whatsapp.py`'s header lists what closing the gap needs, and almost none of it
is code. Writing the cell UNSUPPORTED would say something false about the
product — §23.3 makes WhatsApp the reliability anchor for morning
notifications, and §6.2 says so twice. Writing it IMPLEMENTED would say
something false about the code. DECLARED is the third answer, and it is what
`notifications.whatsapp_rail` reads, so the gate closes itself the day the cell
flips and cannot go stale in either direction.

── What the ladder does with a declared channel ────────────────────────────

Nothing, and that is the point worth stating: `available_channels` filters on
IMPLEMENTED, so a user whose §23.5 matrix has "morning × whatsapp" switched on
still gets her brief — over push, or over email — rather than nothing. Her
preference is kept and honoured on the day the cell flips. A ladder that
treated a declared channel as a rung would fail every message that reached it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

from sitara_schemas.notifications import NOTIFICATION_CHANNELS, NotificationChannel

from sitara_api.notifications.providers.base import ChannelProviderName

logger = logging.getLogger(__name__)


class Support(StrEnum):
    """What we can honestly say about a (provider, channel) cell."""

    #: An adapter exists and has been exercised end to end against the real
    #: protocol — not against a stand-in for it.
    IMPLEMENTED = "implemented"
    #: §23.3 names this channel and no adapter is written. It cannot carry
    #: traffic. This is the state a release gate should watch.
    DECLARED = "declared"
    #: This provider does not serve this channel and never will. Not a gap.
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class Route:
    """The answer, including when the answer is "no one"."""

    provider: ChannelProviderName | None
    support: Support
    #: A message KEY, never a sentence — §2.4 puts every user-facing string in
    #: the catalogs, and this reason reaches S41.
    reason_key: str | None = None

    @property
    def available(self) -> bool:
        return self.provider is not None


#: (provider, channel) → Support.
#:
#: **The one DECLARED row is this milestone's honesty**, and it is deliberately
#: alone. Push and email are not simulated here: web push needs no account at
#: all (the push service is the browser's own and VAPID is a keypair we
#: generate), and SMTP is a protocol whose host is configuration. Both are
#: implemented against the real thing, which is why neither is gated.
CAPABILITIES: dict[tuple[ChannelProviderName, NotificationChannel], Support] = {
    # RFC 8291 + RFC 8292, posted to whatever endpoint the browser supplied.
    # No vendor account exists to be missing. See `webpush.py`.
    (ChannelProviderName.WEB_PUSH_VAPID, NotificationChannel.PUSH): Support.IMPLEMENTED,
    (
        ChannelProviderName.WEB_PUSH_VAPID,
        NotificationChannel.EMAIL,
    ): Support.UNSUPPORTED,
    (
        ChannelProviderName.WEB_PUSH_VAPID,
        NotificationChannel.WHATSAPP,
    ): Support.UNSUPPORTED,
    # Ordinary SMTP: Mailpit locally, SES in production (§23.3). One protocol,
    # one adapter, a host in configuration.
    (ChannelProviderName.SMTP, NotificationChannel.EMAIL): Support.IMPLEMENTED,
    (ChannelProviderName.SMTP, NotificationChannel.PUSH): Support.UNSUPPORTED,
    (ChannelProviderName.SMTP, NotificationChannel.WHATSAPP): Support.UNSUPPORTED,
    # §23.3's BSP path. No account, no approved templates, no adapter — and
    # the templates are the long pole. See `whatsapp.py`.
    (
        ChannelProviderName.WHATSAPP_CLOUD,
        NotificationChannel.WHATSAPP,
    ): Support.DECLARED,
    (ChannelProviderName.WHATSAPP_CLOUD, NotificationChannel.PUSH): Support.UNSUPPORTED,
    (ChannelProviderName.WHATSAPP_CLOUD, NotificationChannel.EMAIL): Support.UNSUPPORTED,
}


#: Preference order per channel. One provider each today; the tuple exists so
#: that a second push provider or a second SMTP relay is a list edit rather
#: than a branch, and so the DECLARED cell is consulted FIRST — which is what
#: keeps it honest rather than decorative. The day WhatsApp's cell flips, it
#: wins without anyone editing this map.
PREFERENCE: dict[NotificationChannel, tuple[ChannelProviderName, ...]] = {
    NotificationChannel.PUSH: (ChannelProviderName.WEB_PUSH_VAPID,),
    NotificationChannel.WHATSAPP: (ChannelProviderName.WHATSAPP_CLOUD,),
    NotificationChannel.EMAIL: (ChannelProviderName.SMTP,),
}


def resolve(channel: NotificationChannel) -> Route:
    """Which adapter may carry this channel.

    Returns a Route with `provider=None` when none may — which is what every
    deployment gets for WhatsApp today, and is the correct answer rather than
    an error.
    """
    best = Support.UNSUPPORTED
    for provider in PREFERENCE.get(channel, ()):
        support = CAPABILITIES.get((provider, channel), Support.UNSUPPORTED)
        if support is Support.IMPLEMENTED:
            return Route(provider=provider, support=support)
        if support is Support.DECLARED:
            best = Support.DECLARED

    if best is Support.DECLARED:
        return Route(
            provider=None,
            support=Support.DECLARED,
            reason_key="notifications.channel_pending",
        )
    return Route(
        provider=None,
        support=Support.UNSUPPORTED,
        reason_key="notifications.channel_unavailable",
    )


def available_channels() -> tuple[NotificationChannel, ...]:
    """The channels that can actually carry a message, in schema order.

    One function, so "we cannot deliver on this channel" is one fact with one
    implementation rather than a condition repeated across the ladder, S41 and
    the dev control surface — the three places it would drift between.
    """
    return tuple(c for c in NOTIFICATION_CHANNELS if resolve(c).available)


def unimplemented_channels() -> tuple[
    tuple[ChannelProviderName, NotificationChannel], ...
]:
    """Every DECLARED cell, for the release gate to name.

    Read rather than listed, so the gate cannot go stale in either direction:
    it closes itself when the last cell flips, and it re-opens if someone adds
    a channel before its adapter.
    """
    return tuple(
        sorted(
            (
                (provider, channel)
                for (provider, channel), support in CAPABILITIES.items()
                if support is Support.DECLARED
            ),
            key=lambda cell: (cell[0].value, cell[1].value),
        )
    )
