"""§23.9's acceptance: the morning brief lands at the user's LOCAL brief_time.

    §23.9 — "timezone matrix delivery tests (IST, EST, GMT, AEDT, half-hour
     zones, DST transition days — briefs land at the local target time in all)"
    §23.8 — "SLO: 95% of morning briefs delivered within 5 min of target time"

This is the milestone's headline claim, so it is measured rather than asserted.
The harness drives the REAL path end to end:

    §7.1 `windows.local_instant`   brief_time + zone + local date → an instant
    §7.1 `notify.build`            → the §6.4 notification row, expiry included
    §23.7 `NotificationStore`      the ledger row, through the real validators
    §23.7 `DeliveryWorker`         ticked minute by minute over a real clock
    §23.3 the ladder + an adapter  the message actually leaving

Nothing is stubbed except the channel, and one case sends through real SMTP to
Mailpit so the whole chain is exercised at least once per run.

── Why the clock is ticked rather than jumped ──────────────────────────────

The question "does it arrive at 07:00 local" is not answered by calling the
worker once at 07:00 — that proves the worker delivers what you hand it. It is
answered by running the worker on every minute across the window and recording
which minute the message left on. That catches the failures that matter: a row
selected an hour early because the expiry was computed against UTC noon, a row
never selected because `scheduled_at` was stored naive, a row delivered twice
because two ticks both claimed it.

── Why the zones are these zones ───────────────────────────────────────────

§23.9 names them, and each one breaks a different naive implementation:

* **IST (+05:30)** and **Asia/Kathmandu (+05:45)** — half-hour and quarter-hour
  offsets. A `timedelta(hours=...)` implementation is wrong here and nowhere
  else, and India is the primary market.
* **America/New_York** — a large negative offset, so the local date and the UTC
  date differ for a morning brief. Anything keyed on a UTC date fires on the
  wrong day.
* **Pacific/Auckland** — the far side of the date line, where "tomorrow" is
  already happening.
* **Europe/London** — where UTC and local coincide half the year, which is what
  makes a UTC bug invisible in the other half.
* **The two DST transition days** — the fall-back repeat (07:00 happens twice)
  and the spring-forward gap (a wall clock that never occurs). §23.9 asks for
  the brief to land "in all" of them, and `windows.local_instant` already
  documents the answer for both; this asserts it through the delivery path.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo

import pytest
from bson import ObjectId
from sitara_schemas.notifications import (
    BRIEF_DELIVERY_SLO_MINUTES,
    NotificationChannel,
    NotificationStatus,
)
from sitara_schemas.today import BriefStatus, Density, Tier

from sitara_api.daily_guidance.notify import NotificationQueue
from sitara_api.daily_guidance.notify import build as build_notification
from sitara_api.daily_guidance.types import Brief
from sitara_api.daily_guidance.windows import local_instant
from sitara_api.notifications.providers.base import ChannelProviderName, PushSubscription
from sitara_api.notifications.providers.email_smtp import SmtpChannel, SmtpConfig
from sitara_api.notifications.store import PreferenceStore, PushSubscriptionStore
from sitara_api.notifications.worker import DeliveryWorker
from tests.notifications.conftest import (
    MAILPIT_SMTP,
    RecordingChannel,
    mailpit_clear,
    mailpit_messages,
    requires_mailpit,
)

pytestmark = pytest.mark.asyncio


@dataclass(frozen=True)
class Case:
    """One row of §23.9's matrix."""

    label: str
    timezone: str
    brief_time: str
    local_date: str
    why: str


#: §23.9's matrix. Every entry names the implementation it breaks.
MATRIX: tuple[Case, ...] = (
    Case(
        "IST",
        "Asia/Kolkata",
        "07:00",
        "2026-08-17",
        "+05:30 — a whole-hour offset implementation is wrong here and nowhere else",
    ),
    Case(
        "Nepal",
        "Asia/Kathmandu",
        "07:00",
        "2026-08-17",
        "+05:45 — the quarter-hour offset a 30-minute rounding survives IST but not this",
    ),
    Case(
        "EST",
        "America/New_York",
        "07:00",
        "2026-08-17",
        "a large negative offset: 07:00 local is 11:00 UTC, so a UTC-keyed day fires wrong",
    ),
    Case(
        "GMT",
        "Europe/London",
        "07:00",
        "2026-08-17",
        "where UTC and local coincide half the year — which is what hides a UTC bug",
    ),
    Case(
        "AEDT",
        "Australia/Sydney",
        "07:00",
        "2026-08-17",
        "the far side: 07:00 Sydney is the PREVIOUS UTC day",
    ),
    Case(
        "Auckland",
        "Pacific/Auckland",
        "06:30",
        "2026-08-17",
        "date line + a half-hour brief time",
    ),
    Case(
        "DST fall-back",
        "America/New_York",
        "01:30",
        "2026-11-01",
        "01:30 happens TWICE; §23.9 wants the brief once, and `local_instant` takes "
        "fold=0 so it is early-in-the-repeat rather than an hour late",
    ),
    Case(
        "DST spring-forward",
        "America/New_York",
        "02:30",
        "2026-03-08",
        "02:30 NEVER HAPPENS; `local_instant` advances to the first wall clock that "
        "does, which is the nearest truth to the target",
    ),
)


def _brief(user_id: str, case: Case) -> Brief:
    """A minimal real `Brief`. The CONTENT is not what is under test here —
    the schedule is — so it carries no modules and a POLISHED status, which is
    what `notify.build` needs to produce a notification at all."""
    return Brief(
        user_id=user_id,
        local_date=case.local_date,
        locale="en",
        density=Density.MED,
        tier=Tier.PAYING,
        status=BriefStatus.POLISHED,
        idempotency_key=f"{user_id}:{case.local_date}:en",
        generated_at=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
    )


async def _seed_user(db, case: Case) -> ObjectId:  # noqa: ANN001
    """One synthetic user in one zone, through the real §6.4 validators."""
    user_id = ObjectId()
    now = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    await db.users.insert_one(
        {
            "_id": user_id,
            "firebase_uid": f"acceptance-{user_id}",
            "status": "active",
            "locale": "en",
            "timezone": case.timezone,
            "email": f"{user_id}@example.invalid",
            "phone": "+919999900002",
            "whatsapp_opted_in": False,
            "synthetic": True,
            "created_at": now,
            "updated_at": now,
            "schema_v": 1,
        }
    )
    await PreferenceStore(db, None).save(
        (await PreferenceStore(db, None).load(str(user_id))).with_brief_time(
            case.brief_time
        ),
        now=now,
    )
    await PushSubscriptionStore(db).upsert(
        user_id=str(user_id),
        subscription=PushSubscription(
            endpoint=f"https://push.invalid/{user_id}", p256dh="p", auth="a"
        ),
        user_agent="acceptance",
        now=now,
    )
    return user_id


async def _tick_until_sent(
    db,  # noqa: ANN001
    service,  # noqa: ANN001
    *,
    due_at: dt.datetime,
    message_id: str,
    window_minutes: int = 20,
) -> dt.datetime | None:
    """Run the REAL worker on every minute around `due_at`.

    Returns the instant the message actually left, or None. Starting the window
    BEFORE the appointment is the point: a row that goes out early is as much a
    failure as one that goes out late, and a harness that began ticking at the
    due time could not see it.
    """
    worker = DeliveryWorker(db, service)
    start = due_at - dt.timedelta(minutes=window_minutes // 2)
    for offset in range(window_minutes):
        tick = start + dt.timedelta(minutes=offset)
        await worker.run(now=tick)
        row = await db.notifications.find_one({"message_id": message_id})
        if row and row["status"] == NotificationStatus.SENT.value:
            return tick
    return None


@pytest.mark.parametrize("case", MATRIX, ids=lambda c: c.label)
async def test_the_brief_lands_at_the_local_brief_time(
    db, make_service, case: Case
) -> None:  # noqa: ANN001
    """§23.9's matrix, one zone at a time, through the real delivery path."""
    user_id = await _seed_user(db, case)
    zone = ZoneInfo(case.timezone)
    hour, minute = (int(part) for part in case.brief_time.split(":"))

    # §7.1's own function. The appointment is computed exactly as the wave
    # computes it — a second implementation here would prove the harness
    # agrees with itself.
    due_at = local_instant(dt.date.fromisoformat(case.local_date), hour, minute, zone)

    notification = build_notification(
        _brief(str(user_id), case), timezone=case.timezone, due_at=due_at
    )
    assert notification is not None
    await NotificationQueue(db).enqueue(notification)

    push = RecordingChannel(
        NotificationChannel.PUSH, ChannelProviderName.WEB_PUSH_VAPID
    )
    sent_at = await _tick_until_sent(
        db,
        make_service({NotificationChannel.PUSH: push}),
        due_at=due_at,
        message_id=notification.message_id,
    )

    assert sent_at is not None, f"{case.label}: never delivered — {case.why}"

    # THE ASSERTION, in the user's own clock. §23.8's SLO is "within 5 min of
    # target time", and the target is a LOCAL wall clock.
    local_sent = sent_at.astimezone(zone)
    drift = abs((sent_at - due_at).total_seconds()) / 60
    assert drift <= BRIEF_DELIVERY_SLO_MINUTES, (
        f"{case.label}: brief_time {case.brief_time}, delivered "
        f"{local_sent:%H:%M} local ({drift:.0f} min out). {case.why}"
    )
    assert len(push.sent) == 1, f"{case.label}: delivered {len(push.sent)} times"


@pytest.mark.parametrize("case", MATRIX, ids=lambda c: c.label)
async def test_the_expiry_is_noon_in_the_users_own_city(db, case: Case) -> None:  # noqa: ANN001
    """§23.4: "morning brief push expires at 12:00 local".

    Mumbai's noon is five and a half hours from London's. An expiry computed in
    UTC would drop a Sydney brief before it was due and hold a New York one
    until the evening — and neither has a symptom until somebody in that city
    stops getting mornings.
    """
    user_id = await _seed_user(db, case)
    zone = ZoneInfo(case.timezone)
    hour, minute = (int(part) for part in case.brief_time.split(":"))
    due_at = local_instant(dt.date.fromisoformat(case.local_date), hour, minute, zone)

    notification = build_notification(
        _brief(str(user_id), case), timezone=case.timezone, due_at=due_at
    )
    assert notification is not None
    local_expiry = notification.expires_at.astimezone(zone)

    if case.brief_time < "12:00":
        assert local_expiry.hour == 12 and local_expiry.minute == 0, case.label
        assert local_expiry.date().isoformat() == case.local_date
    else:
        # §23.4's rule is about staleness, not about censoring a user's own
        # choice: a brief_time after noon anchors its window to the appointment.
        assert notification.expires_at > due_at


async def test_a_brief_that_missed_its_window_is_dropped_not_delivered_late(
    db, make_service
) -> None:  # noqa: ANN001
    """§23.4: "undelivered → dropped, not late-delivered".

    The worker is run at 14:00 local — two hours past noon — on a brief that
    was due at 07:00. Nothing leaves, and the row is retired as `expired`
    rather than sitting queued forever, which is what makes §23.8's delivery
    rate a rate rather than a slowly-growing denominator.
    """
    case = MATRIX[0]
    user_id = await _seed_user(db, case)
    zone = ZoneInfo(case.timezone)
    due_at = local_instant(dt.date.fromisoformat(case.local_date), 7, 0, zone)

    notification = build_notification(
        _brief(str(user_id), case), timezone=case.timezone, due_at=due_at
    )
    assert notification is not None
    await NotificationQueue(db).enqueue(notification)

    push = RecordingChannel(
        NotificationChannel.PUSH, ChannelProviderName.WEB_PUSH_VAPID
    )
    afternoon = local_instant(dt.date.fromisoformat(case.local_date), 14, 0, zone)
    await DeliveryWorker(db, make_service({NotificationChannel.PUSH: push})).run(
        now=afternoon
    )
    assert push.sent == []

    from sitara_api.notifications.store import NotificationStore

    assert await NotificationStore(db).expire_stale(now=afternoon) == 1
    row = await db.notifications.find_one({"message_id": notification.message_id})
    assert row["status"] == NotificationStatus.EXPIRED.value


async def test_a_regenerated_brief_replaces_its_push_rather_than_duplicating(
    db, make_service
) -> None:  # noqa: ANN001
    """§23.4's collapse key, through the enqueue path §32.7 uses.

    §7.1's own worked example is a user who flew to London overnight: the brief
    regenerates, and the OLD push must be retired rather than joined. Two
    morning pushes is the failure §23.9 makes release-blocking.
    """
    case = MATRIX[0]
    user_id = await _seed_user(db, case)
    zone = ZoneInfo(case.timezone)
    due_at = local_instant(dt.date.fromisoformat(case.local_date), 7, 0, zone)
    queue = NotificationQueue(db)

    first = build_notification(
        _brief(str(user_id), case), timezone=case.timezone, due_at=due_at
    )
    assert first is not None
    await queue.enqueue(first)

    # The regenerate: same user, same local date, a later appointment.
    second = build_notification(
        _brief(str(user_id), case),
        timezone=case.timezone,
        due_at=due_at + dt.timedelta(minutes=30),
    )
    assert second is not None and second.message_id != first.message_id
    await queue.enqueue(second)

    push = RecordingChannel(
        NotificationChannel.PUSH, ChannelProviderName.WEB_PUSH_VAPID
    )
    worker = DeliveryWorker(db, make_service({NotificationChannel.PUSH: push}))
    for offset in range(0, 60):
        await worker.run(now=due_at + dt.timedelta(minutes=offset))

    assert len(push.sent) == 1, "a regenerated brief must REPLACE its push, not add one"
    retired = await db.notifications.find_one({"message_id": first.message_id})
    assert retired["status"] == NotificationStatus.SUPERSEDED.value


@requires_mailpit
async def test_the_brief_reaches_a_real_inbox_at_the_local_brief_time(
    db, make_service
) -> None:  # noqa: ANN001
    """The same claim, through a real SMTP server, so the chain is exercised.

    Every other case in this file stops at the adapter boundary. This one runs
    the whole way: §7.1's instant → the ledger row → the worker's tick → an
    SMTP conversation → a message a human can open at http://localhost:8025.
    "The brief arrives at 07:00 in Mumbai" is then something you can look at
    rather than something a counter reports.
    """
    await mailpit_clear()
    case = MATRIX[0]
    user_id = await _seed_user(db, case)
    zone = ZoneInfo(case.timezone)
    due_at = local_instant(dt.date.fromisoformat(case.local_date), 7, 0, zone)

    notification = build_notification(
        _brief(str(user_id), case), timezone=case.timezone, due_at=due_at
    )
    assert notification is not None
    await NotificationQueue(db).enqueue(notification)

    service = make_service(
        {
            NotificationChannel.EMAIL: SmtpChannel(
                SmtpConfig(
                    host=MAILPIT_SMTP[0],
                    port=MAILPIT_SMTP[1],
                    from_address="tara@sitara.localhost",
                )
            )
        }
    )
    sent_at = await _tick_until_sent(
        db, service, due_at=due_at, message_id=notification.message_id
    )
    assert sent_at is not None

    messages = await mailpit_messages()
    assert len(messages) == 1
    assert messages[0]["Subject"] == "Good morning"

    local_sent = sent_at.astimezone(zone)
    assert local_sent.strftime("%H:%M") == case.brief_time
