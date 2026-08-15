"""§23.7's emergency stop, and §12's thirty seconds.

    "Emergency stop (§12) halts queues per class/channel/locale in <30s and is
     drill-tested."

── Why the three axes are three axes ───────────────────────────────────────

Each names a different incident, and an operator who can only halt everything
will hesitate for the seconds that matter:

* **class** — a marketing template is going out with the wrong offer. Halt M
  and the morning briefs keep arriving.
* **channel** — the push service is returning 500s and every retry is making
  it worse. Halt push and §23.3's ladder carries the same messages on email.
* **locale** — a Hindi template landed with a broken interpolation. Halt `hi`
  and English and Hinglish are unaffected.

A halt on any axis stops a message that matches it. They compose by OR and not
by AND, which is the direction that fails safe: an operator who halts `push`
and separately halts `marketing` has stopped both, not merely the marketing
pushes.

── Why this is Redis and why it has no TTL ─────────────────────────────────

§12's number is the reason it is Redis: a halt has to be believed by every
worker in the fleet within thirty seconds, and the only mechanism that does
that without a deploy is shared state every send reads. It is one `SMEMBERS`
against a tiny set on a warm connection.

It has **no expiry**, deliberately. A halt that lapsed on its own would come
back at the worst possible moment — hours after the incident, with nobody
watching, and with the operator believing it was still in force. Resuming is an
act, and `resume` is what performs it.

`halted()` FAILS OPEN when Redis is unreachable, and that is the uncomfortable
choice made deliberately. Failing closed would mean a Redis blip silences every
notification in the product including §23.1's Class T — OTPs, payment failures,
L4 safety resources — for everyone, with no operator involved and no alarm
saying so. §8's degradation ladder says the same thing in general: an outage in
a control plane must not take out the thing it controls. The mitigation is that
a halt is an INCIDENT, with a human watching, and §23.8 alarms on delivery
rates that would show a halt leaking.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sitara_schemas.notifications import (
    EMERGENCY_STOP_SECONDS,
    MessageClass,
    NotificationChannel,
)

logger = logging.getLogger(__name__)

_KEY = "notif:halted"

#: §12's SLA, for the drill to measure against. Every worker reads this set on
#: every send, so the real bound is a Redis round trip — the number is here so
#: `test_emergency_stop.py` asserts a promise rather than an implementation.
DRILL_SECONDS = EMERGENCY_STOP_SECONDS


@dataclass(frozen=True)
class Halt:
    """One halt, on one axis.

    Three optional fields rather than three classes, because the OPERATOR
    thinks in one vocabulary ("stop marketing", "stop push", "stop hi") and the
    axes are otherwise identical. Exactly one is set — a halt naming two axes
    would be an AND, and see the header for why they compose by OR.
    """

    message_class: MessageClass | None = None
    channel: NotificationChannel | None = None
    locale: str | None = None

    def __post_init__(self) -> None:
        named = [f for f in (self.message_class, self.channel, self.locale) if f]
        if len(named) != 1:
            raise ValueError(
                "a halt names exactly ONE axis (§23.7: 'per class/channel/locale'). "
                "A halt naming two would be an AND, and an operator who halted "
                "'push' and 'marketing' expecting both to stop would have stopped "
                "only the marketing pushes."
            )

    @property
    def token(self) -> str:
        if self.message_class:
            return f"class:{self.message_class.value}"
        if self.channel:
            return f"channel:{self.channel.value}"
        return f"locale:{self.locale}"


class EmergencyStop:
    """§23.7's kill switch. §32.3 puts it behind engineering+product."""

    def __init__(self, redis) -> None:  # noqa: ANN001
        self._redis = redis

    async def halt(self, halt: Halt) -> None:
        await self._redis.sadd(_KEY, halt.token)
        logger.warning("notification queue HALTED", extra={"axis": halt.token})

    async def resume(self, halt: Halt) -> None:
        await self._redis.srem(_KEY, halt.token)
        logger.warning("notification queue resumed", extra={"axis": halt.token})

    async def active(self) -> frozenset[str]:
        raw = await self._redis.smembers(_KEY)
        return frozenset(
            token.decode() if isinstance(token, bytes) else str(token) for token in raw
        )

    async def halted(
        self,
        *,
        message_class: MessageClass,
        channel: NotificationChannel | None,
        locale: str,
    ) -> str | None:
        """The axis holding this message, or None.

        Returns the TOKEN rather than a boolean so the `notifications` row and
        the log record which halt stopped it — during an incident, "12,000
        messages held" is much less useful than "12,000 messages held by
        channel:push".
        """
        try:
            active = await self.active()
        except Exception:  # noqa: BLE001
            # Fails OPEN. See the module header — the alternative is a Redis
            # blip silencing every OTP and every L4 safety resource in the
            # product, with nobody having decided that.
            logger.error("emergency-stop state unreadable — failing OPEN (§8)")
            return None

        for token in (
            f"class:{message_class.value}",
            f"locale:{locale}",
            *((f"channel:{channel.value}",) if channel else ()),
        ):
            if token in active:
                return token
        return None
