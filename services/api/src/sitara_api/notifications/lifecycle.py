"""§23.6's token and opt-in lifecycle — pure, and clock-injected.

    "Web-push subscriptions: stored per device with `endpoint`, keys, UA,
     created/last-success; a 410/404 from the push service marks the
     subscription dead immediately; 3 consecutive failures → dead; dead
     subscriptions trigger a silent re-subscribe attempt on next app open, and
     channel routing falls back meanwhile."

No database and no network here, for `payments/lifecycle.py`'s reason: the
interesting cases are a counter that must reset, two ways of dying that are not
the same, and a state the §23.3 ladder has to read correctly while a repair is
pending. All three are cheap to reproduce as values and expensive to reason
about through a collection.

── The two deaths are not one death ────────────────────────────────────────

§23.6 gives two rules and they mean different things:

* **404/410 kills immediately.** The push service is telling us the browser
  discarded this subscription. There is nothing to retry — the endpoint no
  longer identifies anything — and a retry is the one response that is
  certainly wrong.
* **Three CONSECUTIVE failures kill.** A timeout is not evidence the
  subscription is gone; it is evidence the network was bad. Three in a row,
  with no success between, is the point at which "bad network" stops being the
  better explanation.

Collapsing them either kills live subscriptions on a flaky morning or keeps
pushing at an endpoint the browser threw away — and the second failure is the
quiet one, because the push service keeps answering 410 and nothing complains.

**`consecutive` is the load-bearing word.** A cumulative failure count retires
a subscription that has worked every morning for a year and failed three times
across it. Any success resets the counter, which is `record_success`'s whole
job.

── A rejection is NOT a death ──────────────────────────────────────────────

`DeliveryFailure.REJECTED` — a 400, a 401, a 403 — does not touch the counter
at all. The reason is specific and it has bitten real products: a mis-rotated
VAPID key makes every push 403, and a rule that counted rejections would retire
**every subscription in the database** in three mornings, converting a
five-minute configuration fix into a re-subscribe campaign across the whole
user base. So a rejection is logged, alarmed on by §23.8's dead-token rate, and
left alone.

── Revival ─────────────────────────────────────────────────────────────────

§23.6's "silent re-subscribe attempt on next app open" produces the SAME
endpoint when the browser still holds the subscription, which is why
`push_subscriptions` is unique on `endpoint` and why `revive` exists as a
transition rather than a new row: a dead row and its replacement are the same
device, and inserting a second one would leave the §23.3 ladder choosing
between two rows for one browser.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, replace

from sitara_schemas.notifications import (
    PUSH_CONSECUTIVE_FAILURES_DEAD,
    DeliveryFailure,
    PushSubscriptionState,
)

from sitara_api.notifications.providers.base import PushSubscription


@dataclass(frozen=True)
class SubscriptionRecord:
    """One device's push subscription, as §23.6 tracks it."""

    subscription: PushSubscription
    state: PushSubscriptionState = PushSubscriptionState.ACTIVE
    user_agent: str | None = None
    last_success_at: dt.datetime | None = None
    consecutive_failures: int = 0
    dead_at: dt.datetime | None = None
    dead_reason: DeliveryFailure | None = None

    @property
    def live(self) -> bool:
        return self.state is PushSubscriptionState.ACTIVE

    @property
    def needs_resubscribe(self) -> bool:
        """§23.6's "silent re-subscribe attempt on next app open".

        Read by the client bootstrap. A dead row is what makes the attempt
        SILENT — the app already knows this browser once had push, so it can
        re-subscribe without asking for the permission again, which the browser
        has not withdrawn.
        """
        return self.state is PushSubscriptionState.DEAD


def record_success(
    record: SubscriptionRecord, *, now: dt.datetime
) -> SubscriptionRecord:
    """A delivery the push service accepted.

    Resets the counter to zero — that is what makes §23.6's three failures
    CONSECUTIVE rather than cumulative — and revives a subscription that had
    been marked dead. The revival matters: a 410 during an outage is possible,
    and a subscription the service is now accepting is a subscription that
    works, whatever we concluded last week.
    """
    return replace(
        record,
        state=PushSubscriptionState.ACTIVE,
        last_success_at=now,
        consecutive_failures=0,
        dead_at=None,
        dead_reason=None,
    )


def record_failure(
    record: SubscriptionRecord,
    failure: DeliveryFailure,
    *,
    now: dt.datetime,
) -> SubscriptionRecord:
    """§23.6's two death rules, and the one failure that is neither."""
    if failure is DeliveryFailure.SUBSCRIPTION_GONE:
        # Immediately. Not "after the counter reaches three" — the endpoint no
        # longer identifies anything, so two more attempts would be two more
        # 410s and a two-morning delay in falling back.
        return replace(
            record,
            state=PushSubscriptionState.DEAD,
            consecutive_failures=record.consecutive_failures + 1,
            dead_at=now,
            dead_reason=failure,
        )

    if failure is DeliveryFailure.TRANSIENT:
        failures = record.consecutive_failures + 1
        if failures >= PUSH_CONSECUTIVE_FAILURES_DEAD:
            return replace(
                record,
                state=PushSubscriptionState.DEAD,
                consecutive_failures=failures,
                dead_at=now,
                dead_reason=failure,
            )
        return replace(record, consecutive_failures=failures)

    # REJECTED and UNCONFIGURED. Neither is evidence about the subscription —
    # see the module header for what counting a rejection costs. The record is
    # returned untouched rather than "updated with no change", so a store can
    # skip the write.
    return record


def revive(
    record: SubscriptionRecord, subscription: PushSubscription
) -> SubscriptionRecord:
    """§23.6's re-subscribe landing on the same device.

    The keys are replaced as well as the state, because a browser that
    re-subscribes mints a fresh `p256dh`/`auth` pair even when it hands back the
    same endpoint — and encrypting to the OLD keys produces a payload the
    browser silently drops, which looks exactly like a push service that
    accepted the message and never delivered it.
    """
    return SubscriptionRecord(
        subscription=subscription,
        state=PushSubscriptionState.ACTIVE,
        user_agent=record.user_agent,
        last_success_at=record.last_success_at,
        consecutive_failures=0,
    )
