"""Persistence for §23 — the notifications ledger, the tokens, the preferences.

§23.7: "the notification worker writes a single source-of-truth `notifications`
doc per message (status: queued → sent → delivered/failed/expired, provider
ids, trigger id, class, locale, template version)."

**Single source of truth** is the load-bearing phrase. Every question §23 asks
about a message — has it gone, was it capped, did it expire, which channel
carried it, which trigger earned it — is answered from that one document.
Nothing here keeps a second count anywhere; §23.1's caps are `count_documents`
against the ledger, not a Redis counter beside it, because a counter and a
ledger disagree exactly when a worker dies between them, and §23.9 makes a cap
breach release-blocking.

── The cap query is a query, and the day is LOCAL ──────────────────────────

`count_today` takes the user's local date boundaries rather than a UTC day.
§23.1's "3/day" is a promise about the user's day: a UTC window gives a Mumbai
user two different caps depending on the hour, and gives an Auckland user a cap
that resets in the middle of her afternoon.

── The preference cache ────────────────────────────────────────────────────

§23.5: "Changes apply within 60s (preferences cached in Redis with pub/sub
invalidation)."

The cache holds the value IN Redis rather than in each process. That makes the
pub/sub unnecessary for this shape and it is worth saying why rather than
looking like an omission: pub/sub exists to tell OTHER processes to drop their
local copies, and a value that lives in Redis has no local copies — the DELETE
on write is itself the cross-process event, and it is synchronous rather than
best-effort. The 60-second TTL stays as the ceiling on the promise for the one
case the delete does not cover: a write that succeeded in Mongo and whose Redis
delete failed.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from collections.abc import Iterable, Sequence
from typing import Any

from sitara_schemas.notifications import (
    MARKETING_WEEKLY_CAP,
    PREFERENCE_APPLY_SECONDS,
    ContextualTrigger,
    DeliveryFailure,
    MessageClass,
    NotificationCategory,
    NotificationChannel,
    NotificationStatus,
    PushSubscriptionState,
)

from sitara_api.chat_orchestration.store import to_object_id
from sitara_api.db.documents import stamp
from sitara_api.notifications.catalogue import TriggerObservation
from sitara_api.notifications.lifecycle import SubscriptionRecord
from sitara_api.notifications.preferences import Preferences, default_matrix
from sitara_api.notifications.providers.base import PushSubscription
from sitara_api.notifications.quiet_hours import QuietHours

logger = logging.getLogger(__name__)


def _oid(user_id: str):  # noqa: ANN201
    """§6.4 types every `user_id` here as objectId; the modules carry §33.2's
    product identity as a string. One conversion, at the store boundary."""
    return to_object_id(user_id, field_name="notifications.user_id")


# ---------------------------------------------------------------------------
# §23.7's ledger
# ---------------------------------------------------------------------------


class NotificationStore:
    """The `notifications` collection — §23.7's one document per message."""

    def __init__(self, db) -> None:  # noqa: ANN001
        self._db = db

    async def record(
        self,
        *,
        user_id: str,
        message_id: str,
        message_class: MessageClass,
        category: NotificationCategory,
        channel: NotificationChannel,
        locale: str,
        template_id: str,
        template_version: str | None,
        scheduled_at: dt.datetime,
        expires_at: dt.datetime,
        collapse_key: str | None = None,
        trigger_id: ContextualTrigger | None = None,
        status: NotificationStatus = NotificationStatus.QUEUED,
    ) -> bool:
        """Write the row. False when §23.4's unique index has already seen it.

        The duplicate guard is the INDEX and not a preceding read — `payments`
        learned that one the expensive way: between a check and an insert is
        where two workers processing the same message both decide they are
        first. `daily_guidance.notify.NotificationQueue.enqueue` is the same
        shape and stays as it is; this is the general path for everything that
        is not a morning brief.
        """
        from pymongo.errors import DuplicateKeyError

        document = stamp(
            {
                "user_id": _oid(user_id),
                "channel": channel.value,
                "template_id": template_id,
                "template_version": template_version,
                "locale": locale,
                "scheduled_at": scheduled_at,
                "expires_at": expires_at,
                "sent_at": None,
                "opened": False,
                "status": status.value,
                "message_id": message_id,
                "message_class": message_class.value,
                "collapse_key": collapse_key,
                # §23.2: "Every contextual send records its trigger ID — the
                # admin dashboard shows the trigger mix". It is also what
                # `auto_paused` reads, so a send that forgot it is a send that
                # cannot be measured and therefore cannot be paused.
                "trigger_id": trigger_id.value if trigger_id else None,
                "provider_message_id": None,
                # Not in §6.4's cell — a local decision recorded so that
                # §23.8's per-category reporting and S41 can both name the
                # toggle a message was sent under without re-deriving it from
                # the class, which is lossy (two categories share Class C).
                "category": category.value,
            }
        )
        try:
            await self._db.notifications.insert_one(document)
        except DuplicateKeyError:
            logger.info(
                "notification already recorded — not duplicating (§23.4)",
                extra={"message_id": message_id},
            )
            return False
        return True

    async def mark_sent(
        self,
        *,
        user_id: str,
        message_id: str,
        channel: NotificationChannel,
        provider_message_id: str | None,
        now: dt.datetime,
    ) -> None:
        """queued → sent (§23.7).

        `channel` is written as well as the status, because §23.3's ladder may
        have moved the message off the channel it was queued for — and a row
        that still names the queued channel would make §23.8's per-channel
        delivery rate a report about intentions.
        """
        await self._db.notifications.update_one(
            {"user_id": _oid(user_id), "message_id": message_id},
            {
                "$set": {
                    "status": NotificationStatus.SENT.value,
                    "channel": channel.value,
                    "sent_at": now,
                    "provider_message_id": provider_message_id,
                    "updated_at": now,
                }
            },
        )

    async def mark_failed(
        self, *, user_id: str, message_id: str, failure: DeliveryFailure, now: dt.datetime
    ) -> None:
        await self._db.notifications.update_one(
            {"user_id": _oid(user_id), "message_id": message_id},
            {
                "$set": {
                    "status": NotificationStatus.FAILED.value,
                    "failure_reason": failure.value,
                    "updated_at": now,
                }
            },
        )

    async def mark_opened(self, *, user_id: str, message_id: str, now: dt.datetime) -> None:
        """§23.8's open rate, and §23.2's auto-pause input.

        Only ever sets `opened` True — never back to False. An open is an event
        that happened, and a second tap on the same notification is not a
        second open.
        """
        await self._db.notifications.update_one(
            {"user_id": _oid(user_id), "message_id": message_id},
            {"$set": {"opened": True, "updated_at": now}},
        )

    async def count_today(
        self, *, user_id: str, day_start: dt.datetime, day_end: dt.datetime
    ) -> int:
        """§23.1's 3/day cap, counted over the user's OWN day.

        Counts what LEFT — `sent` and `delivered` — and not what was queued.
        A queued row that is about to be superseded or expired never reaches
        anybody, and counting it would spend a cap slot on a message the user
        will not receive. The mirror error is worse and is the one this
        ordering avoids: counting only `delivered` would let three `sent`
        messages sit uncounted while a fourth was admitted.
        """
        return await self._db.notifications.count_documents(
            {
                "user_id": _oid(user_id),
                "sent_at": {"$gte": day_start, "$lt": day_end},
                "status": {
                    "$in": [
                        NotificationStatus.SENT.value,
                        NotificationStatus.DELIVERED.value,
                    ]
                },
            }
        )

    async def count_class_since(
        self, *, user_id: str, message_class: MessageClass, since: dt.datetime
    ) -> int:
        """§23.1's per-class window — Class M's "hard-capped 2/week".

        A ROLLING window, which is why this takes an instant rather than a week
        number: a calendar-week reset lets four marketing messages land inside
        48 hours across a Sunday and satisfies "2/week" both times.
        """
        return await self._db.notifications.count_documents(
            {
                "user_id": _oid(user_id),
                "message_class": message_class.value,
                "sent_at": {"$gte": since},
                "status": {
                    "$in": [
                        NotificationStatus.SENT.value,
                        NotificationStatus.DELIVERED.value,
                    ]
                },
            }
        )

    async def contextual_slot_spent(
        self, *, user_id: str, day_start: dt.datetime, day_end: dt.datetime
    ) -> bool:
        """§23.1's "max 1/day" for Class C, over the user's own day.

        Asks about the CLASS and not about the categories, so the two §23.5
        toggles that both map to Class C share one slot — which is what §23.1
        says and what a per-category count would quietly turn into two.
        """
        return (
            await self._db.notifications.count_documents(
                {
                    "user_id": _oid(user_id),
                    "message_class": MessageClass.CONTEXTUAL.value,
                    "sent_at": {"$gte": day_start, "$lt": day_end},
                    "status": {
                        "$in": [
                            NotificationStatus.SENT.value,
                            NotificationStatus.DELIVERED.value,
                        ]
                    },
                },
                limit=1,
            )
            > 0
        )

    async def due(
        self, *, now: dt.datetime, limit: int = 500
    ) -> Sequence[dict[str, Any]]:
        """Queued rows whose time has come and which have not expired.

        The expiry test is in the QUERY. Selecting due rows and filtering
        expired ones in Python would work and would also mean a worker that
        fell behind picks up a thousand rows it must then drop — §23.4's
        "dropped, not late-delivered" is cheaper and more obviously correct
        when the sweep never loads them.
        """
        cursor = (
            self._db.notifications.find(
                {
                    "status": NotificationStatus.QUEUED.value,
                    "scheduled_at": {"$lte": now},
                    "expires_at": {"$gt": now},
                }
            )
            .sort("scheduled_at", 1)
            .limit(limit)
        )
        return [row async for row in cursor]

    async def expire_stale(self, *, now: dt.datetime) -> int:
        """§23.4: "undelivered → dropped, not late-delivered".

        A status change and not a delete. §6.4 gives `notifications` a 180-day
        TTL and §23.8 reports delivery rates — a deleted row would make a
        morning where every push expired look like a morning with no pushes,
        which is the one reading that hides the problem.
        """
        result = await self._db.notifications.update_many(
            {
                "status": NotificationStatus.QUEUED.value,
                "expires_at": {"$lte": now},
            },
            {
                "$set": {
                    "status": NotificationStatus.EXPIRED.value,
                    "updated_at": now,
                }
            },
        )
        return int(result.modified_count)

    async def trigger_observations(
        self, *, since: dt.datetime, until: dt.datetime
    ) -> list[TriggerObservation]:
        """§23.2's auto-pause input, aggregated across users.

        Across users deliberately: §23.2's rule is about a TRIGGER's copy being
        worth reading, which is a property of the trigger, not of one person's
        fortnight. Per-user rates would also be too sparse to mean anything —
        one contextual message a day for fourteen days is fourteen samples.
        """
        pipeline = [
            {
                "$match": {
                    "trigger_id": {"$ne": None},
                    "sent_at": {"$gte": since, "$lt": until},
                    "status": {
                        "$in": [
                            NotificationStatus.SENT.value,
                            NotificationStatus.DELIVERED.value,
                        ]
                    },
                }
            },
            {
                "$group": {
                    "_id": "$trigger_id",
                    "sent": {"$sum": 1},
                    "opened": {"$sum": {"$cond": ["$opened", 1, 0]}},
                }
            },
        ]
        observations: list[TriggerObservation] = []
        async for row in self._db.notifications.aggregate(pipeline):
            try:
                trigger = ContextualTrigger(row["_id"])
            except ValueError:
                # A trigger id the catalogue no longer knows. Skipped rather
                # than crashed: §23.2's set is closed, so this can only be a
                # row written before a rename, and a fortnight from now it
                # falls out of the window on its own.
                logger.info("unknown trigger id in observations", extra={"id": row["_id"]})
                continue
            observations.append(
                TriggerObservation(
                    trigger=trigger, sent=int(row["sent"]), opened=int(row["opened"])
                )
            )
        return observations


# ---------------------------------------------------------------------------
# §23.6's tokens
# ---------------------------------------------------------------------------


class PushSubscriptionStore:
    """`push_subscriptions` — one row per device (§23.6)."""

    def __init__(self, db) -> None:  # noqa: ANN001
        self._db = db

    async def upsert(
        self,
        *,
        user_id: str,
        subscription: PushSubscription,
        user_agent: str | None,
        now: dt.datetime,
    ) -> None:
        """Register or re-register one browser.

        An upsert on `endpoint`, because §23.6's silent re-subscribe returns
        the SAME endpoint when the browser still holds it — so an insert would
        accumulate a row per app open, and the ladder would then be choosing
        between several rows for one device. The keys are always rewritten:
        a re-subscribe mints a fresh `p256dh`/`auth` pair even on an unchanged
        endpoint, and encrypting to the old pair produces a payload the browser
        silently drops.
        """
        await self._db.push_subscriptions.update_one(
            {"endpoint": subscription.endpoint},
            {
                "$set": {
                    "user_id": _oid(user_id),
                    "p256dh": subscription.p256dh,
                    "auth": subscription.auth,
                    "user_agent": user_agent,
                    "state": PushSubscriptionState.ACTIVE.value,
                    "consecutive_failures": 0,
                    "dead_at": None,
                    "dead_reason": None,
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now, "schema_v": 1, "last_success_at": None},
            },
            upsert=True,
        )

    async def live_for(self, user_id: str) -> list[SubscriptionRecord]:
        """Every ACTIVE subscription this user has, newest-successful first.

        A list rather than one, because §23.6 is per DEVICE: a phone and a
        laptop are two subscriptions and §23.3's push rung means "her push",
        not "one of her browsers". The order puts the device she most recently
        received on first, which is the best available proxy for the one she is
        holding.
        """
        cursor = self._db.push_subscriptions.find(
            {
                "user_id": _oid(user_id),
                "state": PushSubscriptionState.ACTIVE.value,
            }
        ).sort("last_success_at", -1)
        return [_as_record(row) async for row in cursor]

    async def all_for(self, user_id: str) -> list[SubscriptionRecord]:
        """Every subscription including the dead ones — §23.6's re-subscribe
        prompt reads this, and the ladder never does."""
        cursor = self._db.push_subscriptions.find({"user_id": _oid(user_id)})
        return [_as_record(row) async for row in cursor]

    async def save(self, user_id: str, record: SubscriptionRecord, *, now: dt.datetime) -> None:
        """Write back a record `lifecycle` transitioned."""
        await self._db.push_subscriptions.update_one(
            {"endpoint": record.subscription.endpoint},
            {
                "$set": {
                    "user_id": _oid(user_id),
                    "state": record.state.value,
                    "last_success_at": record.last_success_at,
                    "consecutive_failures": record.consecutive_failures,
                    "dead_at": record.dead_at,
                    "dead_reason": (
                        record.dead_reason.value if record.dead_reason else None
                    ),
                    "updated_at": now,
                }
            },
        )

    async def remove(self, *, user_id: str, endpoint: str) -> int:
        """An explicit unsubscribe from the client — the browser told us it is
        going away, which is different from us concluding it has."""
        result = await self._db.push_subscriptions.delete_one(
            {"user_id": _oid(user_id), "endpoint": endpoint}
        )
        return int(result.deleted_count)


def _as_record(row: dict[str, Any]) -> SubscriptionRecord:
    return SubscriptionRecord(
        subscription=PushSubscription(
            endpoint=row["endpoint"], p256dh=row["p256dh"], auth=row["auth"]
        ),
        state=PushSubscriptionState(row.get("state", PushSubscriptionState.ACTIVE.value)),
        user_agent=row.get("user_agent"),
        last_success_at=row.get("last_success_at"),
        consecutive_failures=int(row.get("consecutive_failures", 0)),
        dead_at=row.get("dead_at"),
        dead_reason=(
            DeliveryFailure(row["dead_reason"]) if row.get("dead_reason") else None
        ),
    )


# ---------------------------------------------------------------------------
# §23.5's preference centre
# ---------------------------------------------------------------------------

_PREFERENCE_CACHE_PREFIX = "notif:prefs:"


class PreferenceStore:
    """`notification_preferences`, with §23.5's 60-second cache in front.

    `redis` is optional and its absence is a designed state, not a degraded
    one: the tests and the pure-logic paths run without it, and a missing cache
    means every read goes to Mongo — slower and identical. A cache whose
    absence changed an ANSWER would be a second source of truth.
    """

    def __init__(self, db, redis=None) -> None:  # noqa: ANN001
        self._db = db
        self._redis = redis

    async def load(self, user_id: str) -> Preferences:
        """Her settings, or the declared defaults.

        A user with no row gets `Preferences(user_id)` — §23.5's defaults —
        rather than an error or an empty matrix. An empty matrix would read as
        "everything off" through `allows`, so a new account would silently
        receive nothing at all, and the first symptom would be a morning brief
        that never arrived for exactly the people who had just signed up.
        """
        cached = await self._cache_get(user_id)
        if cached is not None:
            return cached
        row = await self._db.notification_preferences.find_one({"user_id": _oid(user_id)})
        preferences = _as_preferences(user_id, row) if row else Preferences(user_id=user_id)
        await self._cache_put(preferences)
        return preferences

    async def save(self, preferences: Preferences, *, now: dt.datetime) -> None:
        """Write, then invalidate. That ORDER, always.

        Invalidating first leaves a window in which a concurrent read repopulates
        the cache from the OLD document and then holds it for the full 60
        seconds — §23.5 promises the change applies within 60s, and the
        tidier-looking order is precisely how it would not.
        """
        await self._db.notification_preferences.update_one(
            {"user_id": _oid(preferences.user_id)},
            {
                "$set": {
                    "matrix": {
                        f"{category.value}:{channel.value}": enabled
                        for (category, channel), enabled in preferences.matrix.items()
                    },
                    "quiet_hours_start": preferences.quiet_hours.start,
                    "quiet_hours_end": preferences.quiet_hours.end,
                    "brief_time": preferences.brief_time,
                    "paused_until": preferences.paused_until,
                    "follow_timezone": preferences.follow_timezone,
                    "home_timezone": preferences.home_timezone,
                    "quiet_overlap_acknowledged": preferences.quiet_overlap_acknowledged,
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now, "schema_v": 1},
            },
            upsert=True,
        )
        await self._invalidate(preferences.user_id)

    async def _cache_get(self, user_id: str) -> Preferences | None:
        if self._redis is None:
            return None
        raw = await self._redis.get(_PREFERENCE_CACHE_PREFIX + user_id)
        if not raw:
            return None
        try:
            return _as_preferences(user_id, json.loads(raw))
        except (ValueError, KeyError):
            # A cached shape this code no longer understands — a deploy in
            # progress. Falling through to Mongo is right; raising would make a
            # rolling deploy an outage of the preference centre.
            logger.info("dropping unreadable cached preferences", extra={"user": user_id})
            return None

    async def _cache_put(self, preferences: Preferences) -> None:
        if self._redis is None:
            return
        await self._redis.set(
            _PREFERENCE_CACHE_PREFIX + preferences.user_id,
            json.dumps(_as_document(preferences), default=str),
            ex=PREFERENCE_APPLY_SECONDS,
        )

    async def _invalidate(self, user_id: str) -> None:
        if self._redis is None:
            return
        await self._redis.delete(_PREFERENCE_CACHE_PREFIX + user_id)


def _as_document(preferences: Preferences) -> dict[str, Any]:
    return {
        "matrix": {
            f"{category.value}:{channel.value}": enabled
            for (category, channel), enabled in preferences.matrix.items()
        },
        "quiet_hours_start": preferences.quiet_hours.start,
        "quiet_hours_end": preferences.quiet_hours.end,
        "brief_time": preferences.brief_time,
        "paused_until": (
            preferences.paused_until.isoformat() if preferences.paused_until else None
        ),
        "follow_timezone": preferences.follow_timezone,
        "home_timezone": preferences.home_timezone,
        "quiet_overlap_acknowledged": preferences.quiet_overlap_acknowledged,
    }


def _as_preferences(user_id: str, row: dict[str, Any]) -> Preferences:
    """One stored document as a value.

    The matrix starts from the DEFAULTS and is overlaid, never replaced. A
    category or channel added to the schema after this row was written is then
    present with its declared default instead of absent — and an absent pair
    reads as "off", which would silently switch off a category nobody chose to
    disable, for exactly the users who have been here longest.
    """
    matrix = default_matrix()
    for key, enabled in (row.get("matrix") or {}).items():
        category_id, _, channel_id = key.partition(":")
        try:
            pair = (NotificationCategory(category_id), NotificationChannel(channel_id))
        except ValueError:
            continue
        matrix[pair] = bool(enabled)

    paused_until = row.get("paused_until")
    if isinstance(paused_until, str):
        paused_until = dt.datetime.fromisoformat(paused_until)

    quiet = QuietHours(
        start=row.get("quiet_hours_start") or QuietHours().start,
        end=row.get("quiet_hours_end") or QuietHours().end,
    )
    return Preferences(
        user_id=user_id,
        matrix=matrix,
        quiet_hours=quiet,
        brief_time=row.get("brief_time") or Preferences(user_id=user_id).brief_time,
        paused_until=paused_until,
        follow_timezone=bool(row.get("follow_timezone", True)),
        home_timezone=row.get("home_timezone") or "Asia/Kolkata",
        quiet_overlap_acknowledged=row.get("quiet_overlap_acknowledged"),
    )


def marketing_window_start(now: dt.datetime) -> dt.datetime:
    """The start of Class M's rolling week (§23.1's "hard-capped 2/week")."""
    return now - dt.timedelta(days=7)


def local_day_bounds(local_date: str, timezone: str) -> tuple[dt.datetime, dt.datetime]:
    """The user's own day as a UTC half-open interval.

    Every cap in §23.1 is a promise about HER day. A UTC window gives a Mumbai
    user two different caps depending on the hour and resets an Auckland user's
    in the middle of her afternoon.
    """
    from zoneinfo import ZoneInfo

    zone = ZoneInfo(timezone)
    date = dt.date.fromisoformat(local_date)
    start = dt.datetime(date.year, date.month, date.day, tzinfo=zone)
    return start.astimezone(dt.UTC), (start + dt.timedelta(days=1)).astimezone(dt.UTC)


def observations_for(triggers: Iterable[ContextualTrigger]) -> list[TriggerObservation]:
    """Zero-sample observations for triggers that sent nothing in the window.

    `auto_paused` treats a None open rate as "not paused", so these are inert —
    they exist so a caller can report the full catalogue's mix (§23.8) without
    the absent triggers reading as an omission in the dashboard.
    """
    return [TriggerObservation(trigger=t, sent=0, opened=0) for t in triggers]


__all__ = [
    "MARKETING_WEEKLY_CAP",
    "NotificationStore",
    "PreferenceStore",
    "PushSubscriptionStore",
    "local_day_bounds",
    "marketing_window_start",
    "observations_for",
]
