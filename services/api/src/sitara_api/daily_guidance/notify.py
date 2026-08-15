"""Enqueueing the morning brief's notification (§23, §7.1's last box).

    "store `daily_briefings` → notification enqueued for exact local time"

This module writes the §6.4 `notifications` row and nothing else. It does not
send: §23.7's channel sender pools, rate-limit budgets and fallback ladder are
the notification worker's job, and putting delivery here would mean the morning
wave blocked on a WhatsApp BSP.

Four §23 rules are enforced at write time, because each of them is unrecoverable
once a message has gone out:

* **§23.4 expiry.** "morning brief push expires at 12:00 local (undelivered →
  dropped, not late-delivered; the brief itself is in-app regardless)". A brief
  push arriving at four in the afternoon is worse than none: the brief is on
  the Today screen either way, and the push would be telling someone about
  their morning after it ended.
* **§23.4 collapse.** "Collapse keys ensure a re-generated brief replaces,
  never duplicates, its push." The key is the brief's identity — user and local
  date — so §7.1's targeted regenerate and §32.7's locale regenerate both land
  on the same row.
* **§23.4 idempotency.** "Delivery is idempotent on `user+message_id`
  end-to-end". The message id is derived, not random, so a retried enqueue
  computes the same id and collides on the unique index rather than sending a
  second push. §23.9 makes a duplicate delivery release-blocking.
* **§32.6 quiet hours.** "brief_time wins over quiet hours for that single
  send." The brief is an appointment the user made. Every other Class-D and
  Class-C message respects quiet hours absolutely, and this module is the only
  place that exception exists.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

from sitara_schemas.notifications import (
    BRIEF_EXPIRY_LOCAL_HOUR,
    MessageClass,
    NotificationStatus,
)

from sitara_api.daily_guidance.templates import TEMPLATE_VERSION
from sitara_api.daily_guidance.types import Brief, BriefStatus

logger = logging.getLogger(__name__)

#: Re-exported, never redeclared. This module DECLARED `MessageClass`,
#: `NotificationStatus` and the noon expiry hour until M12 — privately, in the
#: daily-guidance package, while §23.5's preference screen was about to name the
#: same sets on the other side of the wire. That is the window in which the
#: confidence states, the presence states, the memory types and the voice
#: vocabulary each drifted, so the sets moved to `sitara_schemas.notifications`
#: before the second declaration existed rather than after a screen rendered the
#: disagreement. The names stay importable from here because §7.1's callers
#: already use them.
__all__ = [
    "BRIEF_EXPIRY_LOCAL_HOUR",
    "BriefNotification",
    "MessageClass",
    "NotificationQueue",
    "NotificationStatus",
    "build",
    "collapse_key_for",
    "expiry_for",
    "message_id_for",
    "revision_for",
    "should_hold_for_regenerate",
]

#: §32.7: "if delivery is <10 min away, the notification waits for the
#: regenerate (never delivers the wrong language)".
REGENERATE_HOLD_MINUTES = 10

#: §23.3's default daily-loop channel order. The row records the channel it was
#: queued for; the worker's fallback ladder may move it, and records that too.
DEFAULT_CHANNEL = "push"


@dataclass(frozen=True)
class BriefNotification:
    user_id: str
    message_id: str
    collapse_key: str
    channel: str
    locale: str
    template_id: str
    scheduled_at: dt.datetime
    expires_at: dt.datetime
    message_class: MessageClass = MessageClass.DAILY_LOOP
    status: NotificationStatus = NotificationStatus.QUEUED
    template_version: str = TEMPLATE_VERSION


def collapse_key_for(user_id: str, local_date: str) -> str:
    """§23.4. Deliberately WITHOUT the locale.

    §32.7 regenerates a brief when the user's language changes, and the whole
    point of the collapse key is that the new push REPLACES the old one. A
    locale in the key would make them two different messages and the user would
    get both — one of them in a language they just stopped reading.
    """
    return f"brief:{user_id}:{local_date}"


def message_id_for(
    user_id: str, local_date: str, locale: str, revision: str = "0"
) -> str:
    """§23.4's idempotency identity. Two properties, and they pull apart.

    §23.4 asks for BOTH of these, and they are not the same key:

    * a RETRY of one enqueue must not send twice — so the id has to be DERIVED,
      never random;
    * a REGENERATE must replace the push — so the id has to CHANGE when the
      brief does, or the replacement collides with the row it is replacing.

    `revision` is what separates them, and it comes from the brief's
    `generated_at`: stable across retries of one generation, different across
    generations. Fixing it at 0 satisfied the first property and quietly broke
    the second — a location change keeps the locale, so it minted the SAME id,
    superseded the queued push, then failed to insert its replacement on the
    unique index and left the user with no morning notification at all. §7.1's
    own worked example ("user flew to London overnight") is that case.
    """
    return f"brief:{user_id}:{local_date}:{locale}:r{revision}"


def revision_for(brief: Brief, scheduled_at: dt.datetime, expires_at: dt.datetime) -> str:
    """A fingerprint of what would actually be DELIVERED.

    Not a clock. `generated_at` was the obvious choice and it is wrong twice:
    two generations inside the same second collide (the acceptance harness does
    exactly that), and a regenerate that changed nothing would still mint a new
    push. Fingerprinting the delivery gets both right by construction —

        same brief, same schedule  → same id → §23.4 dedup, nothing sent twice
        different brief or schedule → new id → §23.4 replacement

    The schedule is in the hash because a location change can leave the text
    untouched and still move the row: §23.4 expires the morning push at 12:00
    LOCAL, and Mumbai's noon is five and a half hours from London's. Keeping
    the old row there would expire the brief against the wrong city.
    """
    material = "|".join(
        [
            brief.status.value,
            scheduled_at.astimezone(dt.UTC).isoformat(),
            expires_at.astimezone(dt.UTC).isoformat(),
            *(f"{m.module.value}={m.rendered}" for m in brief.modules),
        ]
    )
    return hashlib.blake2b(material.encode("utf-8"), digest_size=6).hexdigest()


def expiry_for(local_date: str, timezone: str) -> dt.datetime:
    """12:00 on the brief's own local date, in the user's zone (§23.4)."""
    zone = ZoneInfo(timezone)
    date = dt.date.fromisoformat(local_date)
    return dt.datetime(
        date.year, date.month, date.day, BRIEF_EXPIRY_LOCAL_HOUR, 0, tzinfo=zone
    ).astimezone(dt.UTC)


def build(
    brief: Brief,
    *,
    timezone: str,
    due_at: dt.datetime,
    channel: str = DEFAULT_CHANNEL,
    revision: str | None = None,
) -> BriefNotification | None:
    """The row for this brief's push, or None when there is nothing to announce.

    A FAILED brief gets no notification. §28.2 already covers that state on the
    Today screen (cached brief + honest line), and pushing someone awake to
    tell them their brief did not work is the kind of thing §29.2 exists to
    forbid. A degraded brief DOES notify: it has real content, and §28.2's
    verified-core-cards variant says so on the card itself.
    """
    if brief.status is BriefStatus.FAILED:
        logger.info(
            "no brief notification: brief failed",
            extra={"user_id": brief.user_id, "local_date": brief.local_date},
        )
        return None

    expires_at = expiry_for(brief.local_date, timezone)
    if expires_at <= due_at:
        # A brief_time after noon expires before it is due. §23.4's rule is
        # about staleness, not about censoring a user's own choice, so the
        # window is anchored to the appointment instead of being dropped.
        expires_at = due_at + dt.timedelta(hours=1)

    return BriefNotification(
        user_id=brief.user_id,
        message_id=message_id_for(
            brief.user_id,
            brief.local_date,
            brief.locale,
            revision
            if revision is not None
            else revision_for(brief, due_at, expires_at),
        ),
        collapse_key=collapse_key_for(brief.user_id, brief.local_date),
        channel=channel,
        locale=brief.locale,
        template_id=f"{TEMPLATE_VERSION}.notification",
        scheduled_at=due_at,
        expires_at=expires_at,
        template_version=TEMPLATE_VERSION,
    )


def should_hold_for_regenerate(
    scheduled_at: dt.datetime, now: dt.datetime, *, hold_minutes: int = REGENERATE_HOLD_MINUTES
) -> bool:
    """§32.7: does a pending delivery have to wait for the regenerate?

    "if delivery is <10 min away, the notification waits for the regenerate
    (never delivers the wrong language — §2.4 rule upheld)". True means hold;
    the regenerate then supersedes the row and the new one goes out on time or
    slightly late, which §2.4 prefers to on time and in the wrong language.
    """
    return dt.timedelta(0) <= scheduled_at - now < dt.timedelta(minutes=hold_minutes)


class NotificationQueue:
    """The §6.4 `notifications` collection, written idempotently.

    `enqueue` is safe to call twice with the same brief: the unique index on
    (user_id, message_id) makes the second call a no-op rather than a second
    push, and §23.9 makes that distinction release-blocking rather than
    cosmetic.
    """

    def __init__(self, db) -> None:  # noqa: ANN001
        self._db = db

    async def enqueue(self, notification: BriefNotification) -> bool:
        """Write the row, then retire the ones it replaces. Order matters.

        INSERT FIRST. Superseding first looks tidier — there is never a moment
        when two rows are queued — and it is wrong in the one case that
        matters: if the insert then fails (a retry of the same enqueue hits the
        unique index), the old row has already been retired and the user is
        left with NO push. Inserting first means the worst case is a moment
        with two queued rows, which the collapse key resolves, rather than a
        morning with none.
        """
        from pymongo.errors import DuplicateKeyError

        from sitara_api.db.documents import stamp

        document = stamp(
            {
                "user_id": _oid(notification.user_id),
                "channel": notification.channel,
                "template_id": notification.template_id,
                "template_version": notification.template_version,
                "locale": notification.locale,
                "scheduled_at": notification.scheduled_at,
                "expires_at": notification.expires_at,
                "sent_at": None,
                "opened": False,
                "status": notification.status.value,
                "message_id": notification.message_id,
                "message_class": notification.message_class.value,
                "collapse_key": notification.collapse_key,
                "trigger_id": None,
                "provider_message_id": None,
            }
        )
        try:
            await self._db.notifications.insert_one(document)
        except DuplicateKeyError:
            # The same generation, enqueued twice. §23.4's idempotency doing
            # its job — and nothing is superseded, because nothing changed.
            logger.info(
                "brief notification already queued — not duplicating (§23.4)",
                extra={"message_id": notification.message_id},
            )
            return False

        # §23.4: "a re-generated brief replaces, never duplicates, its push".
        await self.supersede(
            notification.user_id,
            notification.collapse_key,
            keep=notification.message_id,
        )
        return True

    async def supersede(
        self, user_id: str, collapse_key: str, *, keep: str | None = None
    ) -> int:
        """Retire queued rows under this collapse key (§23.4).

        Only QUEUED rows: a message already handed to a provider cannot be
        unsent, and marking it superseded would make §23.8's delivery analytics
        lie about what actually reached the user.

        `keep` excludes the row that is doing the replacing, so `enqueue` can
        insert first and retire the rest without retiring itself.
        """
        query: dict[str, Any] = {
            "user_id": _oid(user_id),
            "collapse_key": collapse_key,
            "status": NotificationStatus.QUEUED.value,
        }
        if keep is not None:
            query["message_id"] = {"$ne": keep}
        result = await self._db.notifications.update_many(
            query,
            {
                "$set": {
                    "status": NotificationStatus.SUPERSEDED.value,
                    "updated_at": dt.datetime.now(dt.UTC),
                }
            },
        )
        return int(result.modified_count)


def _oid(user_id: str):  # noqa: ANN201
    """§6.4 types `notifications.user_id` as objectId; the module carries the
    §33.2 product identity as a string. One conversion, at the store boundary."""
    from sitara_api.chat_orchestration.store import to_object_id

    return to_object_id(user_id, field_name="notifications.user_id")
