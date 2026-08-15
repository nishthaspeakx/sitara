"""§23.3's channel routing and fallback ladder — the per-class state machine.

    "Per-user channel state machine, evaluated per message:
     **Daily-loop:** primary = user's chosen channel (default: push if PWA
     installed + permission granted; else WhatsApp if opted in; else email). If
     push delivery fails or the subscription is expired → silent fallback to
     WhatsApp (if opted in) same message, NOT both — cross-channel dedupe key
     `user+message_id` in Redis, 24h. **Transactional:** OTP → SMS-grade path
     (WhatsApp OTP template + email simultaneously if no phone; push never used
     for OTP); payment/security → all opted-in channels (deliberate
     redundancy). **Marketing:** only the explicitly-consented channel(s), no
     fallback."

Three classes, three DIFFERENT shapes, and the differences are the whole
section. Collapsing them into one "try each channel in turn" list would break
each in its own direction:

* a Class-D brief would go out twice, because "NOT both" is the rule;
* a payment failure would go out ONCE, because redundancy there is deliberate;
* a marketing message would fall back onto a channel nobody consented to.

So the ladder is a `Ladder` value with a MODE, and the mode is chosen by class
in exactly one place.

── The dedupe key is the load-bearing part ─────────────────────────────────

§23.3's `user+message_id` key in Redis for 24h is what makes "NOT both" true
across processes. It matters more than it looks, because the fallback is
attempted precisely when something has gone wrong — a push service timing out
is also a push service that might have delivered — and a retry that reaches a
second channel without the key is a double send. §23.9 makes a duplicate
delivery release-blocking, so this is one of the two rules in §23 that a bug
cannot be walked back from: an unsent message can be sent, and a sent one
cannot be unsent.

The key is deliberately the SAME `message_id` §23.4 derives for idempotency,
and deliberately does NOT include the channel. A per-channel key would be
satisfied by every rung of the ladder separately, which is the exact shape of
the bug it exists to prevent.

── What "primary = user's chosen channel" means here ───────────────────────

§23.3's default order is push → WhatsApp → email, and §23.5's matrix is what
"chosen" means. The two compose rather than competing: the matrix says which
channels are ON, `routing.available_channels` says which can carry anything at
all, `Recipient.reachable_on` says which we have an address for, and the order
is §23.3's. A channel has to pass all three to become a rung.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sitara_schemas.notifications import (
    DEDUPE_WINDOW_HOURS,
    MessageClass,
    NotificationCategory,
    NotificationChannel,
)

from sitara_api.notifications.classes import CLASS_FOR_CATEGORY
from sitara_api.notifications.preferences import Preferences
from sitara_api.notifications.providers.base import Recipient
from sitara_api.notifications.providers.routing import available_channels

#: §23.3's default preference order for the daily loop: "push if PWA installed
#: + permission granted; else WhatsApp if opted in; else email". Written once,
#: read by every mode — the modes differ in what they DO with the order, never
#: in what the order is.
CHANNEL_ORDER: tuple[NotificationChannel, ...] = (
    NotificationChannel.PUSH,
    NotificationChannel.WHATSAPP,
    NotificationChannel.EMAIL,
)

#: §23.3 — "push never used for OTP".
#:
#: A named constant rather than an `if` in the OTP sender, because the rule is
#: about a MESSAGE PURPOSE and not about a class: an OTP and a payment receipt
#: are both Class T and only one of them excludes push. The reason is that a
#: push notification renders on a lock screen, where a one-time code is
#: readable by anyone holding the phone — which is the threat OTP exists to
#: address.
OTP_EXCLUDED_CHANNELS: frozenset[NotificationChannel] = frozenset(
    {NotificationChannel.PUSH}
)


class DeliveryMode(StrEnum):
    """§23.3's three shapes. One per class, and they are not interchangeable."""

    #: Try rungs in order, stop at the first acceptance. §23.3's daily-loop
    #: fallback: "same message, NOT both".
    FIRST_SUCCESS = "first_success"
    #: Send on every rung at once. §23.3's transactional "all opted-in
    #: channels (deliberate redundancy)" — a payment failure that reached only
    #: a dead push subscription is a subscription cancelled in silence.
    FANOUT = "fanout"
    #: Send on the consented rungs and do not fall back off any of them.
    #: §23.3's marketing: "only the explicitly-consented channel(s), no
    #: fallback". A failed marketing send is simply not sent.
    CONSENTED_ONLY = "consented_only"


@dataclass(frozen=True)
class Ladder:
    """The rungs for one message, and what to do with them."""

    mode: DeliveryMode
    channels: tuple[NotificationChannel, ...]
    #: Why there are no rungs, when there are none. §23.3's ladder running out
    #: is an ordinary outcome — a user with no push subscription, no WhatsApp
    #: opt-in and a suppressed email address is unreachable, and the honest
    #: record of that is a `failed` row with a reason rather than a retry loop.
    reason_key: str | None = None

    @property
    def deliverable(self) -> bool:
        return bool(self.channels)


def mode_for(message_class: MessageClass) -> DeliveryMode:
    """§23.3's mode per class. The one place the mapping is made."""
    match message_class:
        case MessageClass.TRANSACTIONAL:
            return DeliveryMode.FANOUT
        case MessageClass.MARKETING:
            return DeliveryMode.CONSENTED_ONLY
        case _:
            return DeliveryMode.FIRST_SUCCESS


def build(
    *,
    category: NotificationCategory,
    preferences: Preferences,
    recipient: Recipient,
    excludes: frozenset[NotificationChannel] = frozenset(),
    message_class: MessageClass | None = None,
) -> Ladder:
    """§23.3's ladder for one message.

    A channel becomes a rung only if it passes all four filters, and each one
    answers a different question:

      §23.5  is it switched ON for this category?          `preferences.allows`
      §23.3  do we have an adapter that can carry it?      `available_channels`
      §23.3  do we have somewhere to send it?              `reachable_on`
      §23.3  is this purpose barred from it?               `excludes`

    Keeping them separate is what lets a user's "morning × whatsapp" toggle
    survive WhatsApp being unimplemented, and lets her push preference survive
    her declining the browser permission. Merged into one boolean, either
    absence would silently rewrite her settings.

    **`message_class` is a parameter and not a derivation**, and it has to be.
    Deriving it from the category here was a real defect: §23.2(1)'s user
    reminder is delivered under the CONTEXTUAL category and is Class T, so a
    ladder that read `CLASS_FOR_CATEGORY[category]` gave it Class C's
    FIRST_SUCCESS mode — the reminder someone explicitly asked for would go to
    one channel and stop, while §23.3 says a Class-T message fans out to all of
    them for deliberate redundancy. Nothing about the failure was visible: the
    reminder still arrived, on one channel, exactly as a daily-loop message
    would. `SendRequest.message_class` is the one place the class is decided,
    and passing it in is what keeps it that way. The default preserves the
    category rule for callers who have no trigger.
    """
    message_class = message_class or CLASS_FOR_CATEGORY[category]
    carriable = set(available_channels())

    channels = tuple(
        channel
        for channel in CHANNEL_ORDER
        if channel not in excludes
        and channel in carriable
        and preferences.allows(category, channel)
        and recipient.reachable_on(channel)
    )

    if not channels:
        return Ladder(
            mode=mode_for(message_class),
            channels=(),
            reason_key=_why_empty(
                category=category,
                preferences=preferences,
                recipient=recipient,
                carriable=carriable,
                excludes=excludes,
            ),
        )
    return Ladder(mode=mode_for(message_class), channels=channels)


def _why_empty(
    *,
    category: NotificationCategory,
    preferences: Preferences,
    recipient: Recipient,
    carriable: set[NotificationChannel],
    excludes: frozenset[NotificationChannel],
) -> str:
    """Which of the four filters emptied the ladder.

    Worth distinguishing because the three answers need three different things
    from a human: "you have switched everything off" is a preference-centre
    sentence, "we cannot reach you anywhere" is a settings prompt to add an
    address, and "no channel is available" is an operations problem the user
    can do nothing about. A single `unreachable` would send all three people to
    the same unhelpful screen.
    """
    switched_on = {
        c for c in CHANNEL_ORDER if preferences.allows(category, c) and c not in excludes
    }
    if not switched_on:
        return "notifications.all_channels_off"
    if not switched_on & carriable:
        return "notifications.channel_unavailable"
    return "notifications.no_reachable_address"


def dedupe_key(user_id: str, message_id: str) -> str:
    """§23.3's cross-channel key: `user+message_id`, and no channel in it.

    A channel in the key would make the key satisfied separately by every rung
    — which is the double send it exists to prevent.
    """
    return f"notif:sent:{user_id}:{message_id}"


#: §23.3 — "in Redis, 24h".
DEDUPE_TTL_SECONDS = DEDUPE_WINDOW_HOURS * 3600


class Dedupe:
    """The 24h cross-channel guard, over Redis (§23.3).

    `claim` is a SET NX EX and the atomicity is the whole point: between a GET
    and a SET is where two workers retrying the same message both decide they
    are the first. It is the same instinct as `payments.store.record_event`
    catching `DuplicateKeyError` rather than reading first — the guard is the
    database operation, never the code around it.
    """

    def __init__(self, redis, *, ttl_seconds: int = DEDUPE_TTL_SECONDS) -> None:  # noqa: ANN001
        self._redis = redis
        self._ttl = ttl_seconds

    async def claim(self, user_id: str, message_id: str) -> bool:
        """True if THIS caller may send. False means someone already did."""
        return bool(
            await self._redis.set(
                dedupe_key(user_id, message_id), "1", nx=True, ex=self._ttl
            )
        )

    async def release(self, user_id: str, message_id: str) -> None:
        """Give the claim back when no rung accepted the message.

        Without this, a message that failed on every channel would hold its key
        for 24 hours and could never be retried — the dedupe key is meant to
        stop a SECOND delivery, not to stop a first one from ever happening.
        """
        await self._redis.delete(dedupe_key(user_id, message_id))
