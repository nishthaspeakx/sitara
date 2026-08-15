"""§23.7's delivery worker — queued rows out of the ledger and onto a channel.

The morning brief is ENQUEUED by §7.1 (`daily_guidance.notify` writes the row
at generation time, for the user's exact local `brief_time`) and DELIVERED
here. That split is §7.1's own design and the reason is in its last box: the
wave must not block on a channel. A brief whose composition waited on an SMTP
handshake would spend its §7.1 budget on transport, and a slow channel would
push the tail of the wave past the appointment it exists to keep.

── Why this does not re-run §23's gates ────────────────────────────────────

`NotificationService.send` ran quiet hours, the caps and the ladder when the
message was ADMITTED. Re-running them here would evaluate the same rules
against a later clock, and the failure that produces is specific and silent: a
brief admitted at 06:55 for a 07:00 appointment would be re-tested at 07:00,
and a user whose quiet hours end at 07:00 would have her brief refused by the
gate that had just let it through. §32.6's exemption has the same shape — it is
about the appointment, and the appointment is a fact about admission.

Two things ARE re-checked, and they are exactly the two that may legitimately
change between admission and delivery:

* **§23.4's expiry**, in the query. A row whose moment has passed is never
  loaded, so "dropped, not late-delivered" costs nothing.
* **§23.7's emergency stop**, per row. It is an operator saying "stop" and it
  has to reach messages that are already in flight — a halt that only applied
  to future admissions would leave the queue draining through the incident.

── Failures are per row ────────────────────────────────────────────────────

One row's channel failing must not stop the wave. `run` catches per row and
records; a batch that aborted on the first bad address would leave the rest of
a city's morning in the queue behind one suppressed mailbox.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field
from typing import Any

from sitara_schemas.notifications import (
    ContextualTrigger,
    MessageClass,
    NotificationCategory,
    NotificationChannel,
    NotificationStatus,
)

from sitara_api.localisation import MissingString
from sitara_api.notifications.service import NotificationService, SendRequest

logger = logging.getLogger(__name__)


@dataclass
class DispatchReport:
    """What one pass did. §23.8 reads the shape of this, not the rows."""

    considered: int = 0
    sent: int = 0
    halted: int = 0
    failed: int = 0
    skipped: int = 0
    channels: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "considered": self.considered,
            "sent": self.sent,
            "halted": self.halted,
            "failed": self.failed,
            "skipped": self.skipped,
            "channels": dict(self.channels),
        }


class DeliveryWorker:
    """Drains `notifications` rows that are due (§23.7)."""

    def __init__(self, db, service: NotificationService) -> None:  # noqa: ANN001
        self._db = db
        self._service = service

    async def run(self, *, now: dt.datetime, limit: int = 500) -> DispatchReport:
        from sitara_api.notifications.store import NotificationStore

        store = NotificationStore(self._db)
        report = DispatchReport()

        for row in await store.due(now=now, limit=limit):
            report.considered += 1
            try:
                result = await self._deliver_row(row, now=now)
            except MissingString:
                # §2.4: no English fallback. The row stays queued and expires on
                # its own schedule rather than going out in the wrong language;
                # `verify_catalogs` means this should be unreachable in a booted
                # process, so it is logged as the configuration error it is.
                report.failed += 1
                logger.error(
                    "notification copy missing at delivery time",
                    extra={"message_id": row.get("message_id")},
                )
                continue
            except Exception:  # noqa: BLE001
                # Per row, deliberately — see the module header. One suppressed
                # mailbox must not hold a city's morning in the queue.
                report.failed += 1
                logger.exception(
                    "notification delivery raised",
                    extra={"message_id": row.get("message_id")},
                )
                continue

            if result is None:
                report.skipped += 1
            elif result.blocked is not None:
                if result.halt_token:
                    report.halted += 1
                else:
                    report.skipped += 1
            elif result.sent:
                report.sent += 1
                for channel in result.channels:
                    report.channels[channel.value] = (
                        report.channels.get(channel.value, 0) + 1
                    )
            else:
                report.failed += 1

        return report

    async def _deliver_row(self, row: dict[str, Any], *, now: dt.datetime):  # noqa: ANN202
        """One queued row, back through the service that admitted it.

        Reconstructing a `SendRequest` from the row rather than carrying a
        payload on the queue: §23.7 makes the document the single source of
        truth, and a queue message holding its own copy of the locale, the
        template and the expiry would be a second one — disagreeing exactly
        when §32.7 regenerates a brief in a new language between enqueue and
        delivery.
        """
        subject = await self._subject_for(row["user_id"])
        if subject is None:
            logger.warning(
                "queued notification for a user with no schedulable profile",
                extra={"message_id": row.get("message_id")},
            )
            return None

        category = _category_of(row)
        trigger = (
            ContextualTrigger(row["trigger_id"]) if row.get("trigger_id") else None
        )
        request = SendRequest(
            user_id=str(row["user_id"]),
            category=category,
            locale=row["locale"],
            timezone=subject["timezone"],
            message_id=row["message_id"],
            params=row.get("params") or {},
            trigger=trigger,
            collapse_key=row.get("collapse_key"),
            scheduled_at=row["scheduled_at"],
            expires_at=row["expires_at"],
        )
        return await self._service.send(request, now=now)

    async def _subject_for(self, user_id) -> dict[str, Any] | None:  # noqa: ANN001
        """The user's zone, which every §23 clock is measured in.

        Read from `users` rather than carried on the row, for §32.7's reason
        applied to geography: a brief enqueued before an overnight flight and
        delivered after it must expire against the city she woke up in
        (§23.4's noon is LOCAL), and a zone frozen at enqueue time would expire
        it against the one she left.
        """
        row = await self._db.users.find_one({"_id": user_id})
        if row is None or not row.get("timezone"):
            return None
        return {"timezone": row["timezone"]}


def _category_of(row: dict[str, Any]) -> NotificationCategory:
    """The §23.5 toggle this row was sent under.

    Written on the row by `store.record` since M12. Rows older than that have
    no `category`, so it is derived from the class — lossy for Class C, which
    two categories share, and `contextual` is the safe side of that loss: it is
    the more restrictive toggle, so a festival greeting from an old row is
    suppressed by a user who switched contextual off rather than being sent to
    someone who switched festivals off.
    """
    stored = row.get("category")
    if stored:
        try:
            return NotificationCategory(stored)
        except ValueError:
            pass
    message_class = MessageClass(row["message_class"])
    return {
        MessageClass.DAILY_LOOP: NotificationCategory.MORNING,
        MessageClass.CONTEXTUAL: NotificationCategory.CONTEXTUAL,
        MessageClass.MARKETING: NotificationCategory.MARKETING,
    }.get(message_class, NotificationCategory.CONTEXTUAL)


__all__ = [
    "DeliveryWorker",
    "DispatchReport",
    "NotificationChannel",
    "NotificationStatus",
]
