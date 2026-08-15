"""§23's control surface — dev only. Fire any notification, on demand.

    GET  /v1/dev/notifications/state         what would happen right now
    POST /v1/dev/notifications/fire          any category or trigger
    POST /v1/dev/notifications/brief         the §7.1 morning push, now
    POST /v1/dev/notifications/cap           send until §23.1's 3/day bites
    POST /v1/dev/notifications/halt          §23.7's emergency stop
    POST /v1/dev/notifications/resume
    POST /v1/dev/notifications/kill-push     retire the push subscription
    POST /v1/dev/notifications/dispatch      drain the queue now
    POST /v1/dev/notifications/reset

This is what makes §23 demonstrable by hand. "Show me the fallback ladder",
"show me the cap", "show me a message held by quiet hours", "show me the brief
arriving inside quiet hours because §32.6 says it may" are each one call, and
every one of them drives the REAL service through the REAL gates. Nothing here
is a shortcut past the code the demo is showing.

── Four rules it does not break ────────────────────────────────────────────

**1. It is mounted only in dev.** `app.py` gates it on `environment == "dev"`,
the same gate `db.seed`, the local CSFLE KMS, `daily_guidance.dev_router` and
`payments.dev_router` all sit behind. A surface that can send a person a
message is not one to leave reachable.

**2. Every fire goes through `NotificationService.send`.** Not through an
adapter directly. §23's gates — the halt, the pause, quiet hours, the three
caps, the ladder, the dedupe key — are the thing worth demonstrating, and a
control surface that called past them would let a demo show a delivery the
product would have refused. `/fire` can therefore RETURN A REFUSAL, and that is
a feature: `blocked: "quiet_hours"` on screen is the spec working.

**3. It never touches a release gate.** `release_gates.py` does not import this
module and `notifications.whatsapp_channel` reads the capability matrix, which
nothing here writes. §23.3's WhatsApp cell stays DECLARED however much of the
flow gets demonstrated — the same rule `prototype.py` states about §33.5 and
`payments/dev_router.py` about §30.3.

**4. `/cap` does not fabricate rows.** It sends real messages through the real
service until §23.1 refuses one, and reports which attempt was refused. Writing
three rows straight into the ledger would demonstrate the QUERY and not the
cap, and the two have been different before — the count deliberately excludes
`queued` and `superseded`, which a hand-written row would not know.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sitara_schemas import ErrorCode
from sitara_schemas.notifications import (
    DAILY_CAP,
    ContextualTrigger,
    DeliveryFailure,
    MessageClass,
    NotificationCategory,
    NotificationChannel,
)

from sitara_api.auth.router import CurrentSession
from sitara_api.errors import ApiError
from sitara_api.notifications.catalogue import CATALOGUE
from sitara_api.notifications.classes import CLASS_FOR_CATEGORY, policy
from sitara_api.notifications.emergency_stop import EmergencyStop, Halt
from sitara_api.notifications.ladder import OTP_EXCLUDED_CHANNELS
from sitara_api.notifications.ladder import build as build_ladder
from sitara_api.notifications.lifecycle import record_failure
from sitara_api.notifications.providers.routing import (
    CAPABILITIES,
    available_channels,
    resolve,
)
from sitara_api.notifications.quiet_hours import local_time_of, may_send, overlaps
from sitara_api.notifications.service import SendRequest
from sitara_api.notifications.store import PreferenceStore, PushSubscriptionStore
from sitara_api.notifications.worker import DeliveryWorker

router = APIRouter(prefix="/v1/dev/notifications", tags=["dev"])


class FireBody(BaseModel):
    """One notification, as an operator would describe it.

    `category` and `trigger` are both offered because §23 has two doors into a
    send and they behave differently: a category is a §23.5 toggle and a
    trigger is a §23.2 catalogue entry that also carries a class — which is how
    `user_reminder` ends up Class T and exempt from both quiet hours and the
    contextual slot. A demo that could only fire categories could not show
    that.
    """

    category: NotificationCategory = NotificationCategory.CONTEXTUAL
    trigger: ContextualTrigger | None = None
    #: Copy slots. Plain data only — no notification interpolates a claim.
    params: dict[str, Any] = Field(default_factory=dict)
    #: Defaults to now. Set it to demonstrate quiet hours without waiting for
    #: 22:30: `"2026-08-15T18:00:00+00:00"` is 23:30 in Asia/Kolkata.
    at: dt.datetime | None = None
    #: §23.3's per-purpose exclusion. `true` demonstrates "push never used for
    #: OTP" without needing an OTP.
    as_otp: bool = False


class HaltBody(BaseModel):
    message_class: MessageClass | None = None
    channel: NotificationChannel | None = None
    locale: str | None = None


def _service(request: Request):  # noqa: ANN202
    service = getattr(request.app.state, "notifications", None)
    if service is None:
        raise ApiError(ErrorCode.SYS_UNAVAILABLE, "errors.sys.unavailable")
    return service


async def _subject(request: Request, user_id: str) -> dict[str, Any]:
    from sitara_api.chat_orchestration.store import to_object_id

    row = await request.app.state.db.users.find_one(
        {"_id": to_object_id(user_id, field_name="users._id")}
    )
    if row is None:
        raise ApiError(ErrorCode.SYS_VALIDATION, "errors.sys.validation")
    return {
        "locale": row.get("locale", "en"),
        # §23's every clock is local. A user row with no zone would silently
        # become UTC and the whole demo would be an hour or five and a half out.
        "timezone": row.get("timezone", "Asia/Kolkata"),
    }


@router.get("/state")
async def state(request: Request, session: CurrentSession) -> dict[str, Any]:
    """What §23 would do for this user right now, without sending anything.

    The single most useful call on this surface: it answers "why did nothing
    arrive" before anyone has to read a log. Every field is computed by the
    same functions the sender uses — this is a view of the rules, not a second
    implementation of them.
    """
    user_id, _ = session
    subject = await _subject(request, str(user_id))
    now = dt.datetime.now(dt.UTC)
    store = PreferenceStore(request.app.state.db, getattr(request.app.state, "redis", None))
    preferences = await store.load(str(user_id))
    local_time = local_time_of(now, subject["timezone"])

    recipient = await _service(request)._recipients.resolve(str(user_id))  # noqa: SLF001
    halted = await EmergencyStop(request.app.state.redis).active()

    return {
        "now_local": local_time,
        "timezone": subject["timezone"],
        "locale": subject["locale"],
        "brief_time": preferences.brief_time,
        "quiet_hours": {
            "start": preferences.quiet_hours.start,
            "end": preferences.quiet_hours.end,
            "now_inside": preferences.quiet_hours.covers(local_time),
            # §32.6, surfaced: the brief lands inside quiet hours and goes
            # anyway. This is the line a demo should point at.
            "brief_overlaps": overlaps(preferences.quiet_hours, preferences.brief_time),
            "brief_would_send_now": may_send(
                category=NotificationCategory.MORNING,
                local_time=preferences.brief_time,
                quiet_hours=preferences.quiet_hours,
                brief_time=preferences.brief_time,
            ).exempt,
        },
        "paused_until": preferences.paused_until,
        "reachable": {
            "push": recipient.reachable_on(NotificationChannel.PUSH),
            "whatsapp": recipient.reachable_on(NotificationChannel.WHATSAPP),
            "email": recipient.reachable_on(NotificationChannel.EMAIL),
        },
        "channels": {
            channel.value: {
                "available": resolve(channel).available,
                "support": resolve(channel).support.value,
            }
            for channel in NotificationChannel
        },
        "ladders": {
            category.value: {
                "class": CLASS_FOR_CATEGORY[category].value,
                "channels": [
                    c.value
                    for c in build_ladder(
                        category=category,
                        preferences=preferences,
                        recipient=recipient,
                    ).channels
                ],
                "mode": build_ladder(
                    category=category, preferences=preferences, recipient=recipient
                ).mode.value,
            }
            for category in NotificationCategory
        },
        "halted": sorted(halted),
        "capability_matrix": {
            f"{provider.value}/{channel.value}": support.value
            for (provider, channel), support in sorted(
                CAPABILITIES.items(), key=lambda kv: (kv[0][0].value, kv[0][1].value)
            )
        },
        "triggers": {
            trigger.value: {
                "priority": spec.priority,
                "class": spec.message_class.value,
                "consumes_slot": spec.consumes_slot,
                "category": spec.category.value,
                "ttl": spec.ttl_rule.value,
            }
            for trigger, spec in CATALOGUE.items()
        },
    }


@router.post("/fire")
async def fire(
    body: FireBody, request: Request, session: CurrentSession
) -> dict[str, Any]:
    """Send one notification of any class or trigger, now.

    Returns the §23 verdict rather than raising on a refusal — a demo that
    404'd when quiet hours held a message would be hiding the thing worth
    seeing.
    """
    user_id, _ = session
    subject = await _subject(request, str(user_id))
    now = dt.datetime.now(dt.UTC)
    at = body.at or now

    category = (
        CATALOGUE[body.trigger].category if body.trigger is not None else body.category
    )
    result = await _service(request).send(
        SendRequest(
            user_id=str(user_id),
            category=category,
            locale=subject["locale"],
            timezone=subject["timezone"],
            # Derived from the instant, so firing twice in the same second is
            # §23.4's idempotency doing its job rather than two pushes — and
            # firing twice a second apart is two, which is what a cap demo
            # needs.
            message_id=f"dev:{category.value}:{int(at.timestamp())}",
            params=_default_params(category, body.trigger) | body.params,
            trigger=body.trigger,
            scheduled_at=at,
            excludes=OTP_EXCLUDED_CHANNELS if body.as_otp else frozenset(),
        ),
        now=now,
    )
    return _as_wire(result)


@router.post("/brief")
async def brief(request: Request, session: CurrentSession) -> dict[str, Any]:
    """The §7.1 morning push, fired at the user's own `brief_time`.

    `scheduled_at` is set to TODAY'S brief_time in her zone rather than to now,
    which is what makes this the §32.6 demonstration: if her brief time sits
    inside her quiet hours the message goes out anyway and the result says
    `quiet_hours_exempt: true`. Firing it at "now" would demonstrate an
    ordinary send and prove nothing about the appointment.
    """
    user_id, _ = session
    subject = await _subject(request, str(user_id))
    now = dt.datetime.now(dt.UTC)
    store = PreferenceStore(request.app.state.db, getattr(request.app.state, "redis", None))
    preferences = await store.load(str(user_id))

    from zoneinfo import ZoneInfo

    zone = ZoneInfo(subject["timezone"])
    local_now = now.astimezone(zone)
    hour, minute = (int(part) for part in preferences.brief_time.split(":"))
    at = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    result = await _service(request).send(
        SendRequest(
            user_id=str(user_id),
            category=NotificationCategory.MORNING,
            locale=subject["locale"],
            timezone=subject["timezone"],
            message_id=f"dev:brief:{local_now.date().isoformat()}:{int(now.timestamp())}",
            collapse_key=f"brief:{user_id}:{local_now.date().isoformat()}",
            scheduled_at=at.astimezone(dt.UTC),
            expires_at=at.replace(hour=12, minute=0).astimezone(dt.UTC),
        ),
        now=now,
    )
    return {
        "brief_time": preferences.brief_time,
        "scheduled_local": at.strftime("%H:%M"),
        "inside_quiet_hours": preferences.quiet_hours.covers(preferences.brief_time),
        **_as_wire(result),
    }


@router.post("/cap")
async def cap(request: Request, session: CurrentSession) -> dict[str, Any]:
    """§23.9's own acceptance case: "attempt 5 sends → exactly 3 + T-class".

    Sends five real Class-D messages and one Class-T, through the real service,
    and reports what each attempt did. Nothing is written by hand — see rule 4
    in the module header.
    """
    user_id, _ = session
    subject = await _subject(request, str(user_id))
    now = dt.datetime.now(dt.UTC)
    service = _service(request)

    attempts = []
    for index in range(5):
        result = await service.send(
            SendRequest(
                user_id=str(user_id),
                category=NotificationCategory.CONTEXTUAL,
                locale=subject["locale"],
                timezone=subject["timezone"],
                message_id=f"dev:cap:{int(now.timestamp())}:{index}",
                params=_default_params(NotificationCategory.CONTEXTUAL, None),
                scheduled_at=now,
            ),
            now=now,
        )
        attempts.append(_as_wire(result))

    # §23.1's Class T, after the cap has bitten. It must still arrive.
    transactional = await service.send(
        SendRequest(
            user_id=str(user_id),
            category=NotificationCategory.CONTEXTUAL,
            locale=subject["locale"],
            timezone=subject["timezone"],
            message_id=f"dev:cap:{int(now.timestamp())}:t",
            params=_default_params(NotificationCategory.CONTEXTUAL, None)
            | {"note": "a reminder you asked for"},
            trigger=ContextualTrigger.USER_REMINDER,
            scheduled_at=now,
        ),
        now=now,
    )

    sent = sum(1 for a in attempts if a["sent"])
    return {
        "daily_cap": DAILY_CAP,
        "attempts": attempts,
        "sent": sent,
        "transactional_after_cap": _as_wire(transactional),
        # The §23.9 assertion, stated on the response so a demo does not have
        # to count. Class C is additionally capped at 1/day, so the honest
        # expectation is ONE contextual plus the Class-T reminder — not three.
        "spec_expectation": (
            "§23.1 caps Class C at 1/day and all classes at 3/day; the Class-T "
            "reminder is exempt from both and must still arrive"
        ),
    }


@router.post("/halt")
async def halt(
    body: HaltBody, request: Request, session: CurrentSession
) -> dict[str, Any]:
    """§23.7's emergency stop, on one axis (§32.3: engineering+product)."""
    stop = EmergencyStop(request.app.state.redis)
    try:
        await stop.halt(
            Halt(
                message_class=body.message_class, channel=body.channel, locale=body.locale
            )
        )
    except ValueError as exc:
        raise ApiError(ErrorCode.SYS_VALIDATION, "errors.sys.validation") from exc
    return {"halted": sorted(await stop.active())}


@router.post("/resume")
async def resume(
    body: HaltBody, request: Request, session: CurrentSession
) -> dict[str, Any]:
    stop = EmergencyStop(request.app.state.redis)
    await stop.resume(
        Halt(message_class=body.message_class, channel=body.channel, locale=body.locale)
    )
    return {"halted": sorted(await stop.active())}


@router.post("/kill-push")
async def kill_push(request: Request, session: CurrentSession) -> dict[str, Any]:
    """§23.6's 410, without needing a push service to send one.

    This is the fallback-ladder demonstration: retire the subscription the way
    a 404/410 does, then fire a brief and watch it arrive on email instead —
    §23.3's "silent fallback … same message, NOT both". It drives
    `lifecycle.record_failure` rather than writing `state: dead` directly, so
    what the demo shows is the rule and not a field.
    """
    user_id, _ = session
    store = PushSubscriptionStore(request.app.state.db)
    now = dt.datetime.now(dt.UTC)
    killed = []
    for record in await store.live_for(str(user_id)):
        updated = record_failure(record, DeliveryFailure.SUBSCRIPTION_GONE, now=now)
        await store.save(str(user_id), updated, now=now)
        killed.append(record.subscription.endpoint[:60])
    return {"killed": killed, "note": "§23.6 — 410/404 marks a subscription dead immediately"}


@router.post("/dispatch")
async def dispatch(request: Request, session: CurrentSession) -> dict[str, Any]:
    """Drain the queue now, instead of waiting for Beat's one-minute tick."""
    now = dt.datetime.now(dt.UTC)
    report = await DeliveryWorker(request.app.state.db, _service(request)).run(now=now)
    return report.as_dict()


@router.post("/reset")
async def reset(request: Request, session: CurrentSession) -> dict[str, Any]:
    """Back to a clean slate for the next run of the walkthrough.

    Scoped by user id, never a collection drop — a dev database is also where
    somebody else's half-finished work lives. `payments/dev_router.py` states
    the same rule and it is the same database.
    """
    user_id, _ = session
    from sitara_api.chat_orchestration.store import to_object_id

    oid = to_object_id(str(user_id), field_name="user_id")
    db = request.app.state.db
    notifications = await db.notifications.delete_many({"user_id": oid})
    preferences = await db.notification_preferences.delete_many({"user_id": oid})
    # Push subscriptions deliberately SURVIVE. They belong to a browser rather
    # than to a demo run, and deleting them means re-granting the notification
    # permission by hand before the next walkthrough — which is the one step of
    # this that a person cannot script.
    stop = EmergencyStop(request.app.state.redis)
    for token in await stop.active():
        kind, _, value = token.partition(":")
        await stop.resume(
            Halt(
                message_class=MessageClass(value) if kind == "class" else None,
                channel=NotificationChannel(value) if kind == "channel" else None,
                locale=value if kind == "locale" else None,
            )
        )
    return {
        "notifications": notifications.deleted_count,
        "preferences": preferences.deleted_count,
        "push_subscriptions_kept": len(
            await PushSubscriptionStore(db).all_for(str(user_id))
        ),
    }


def _default_params(
    category: NotificationCategory, trigger: ContextualTrigger | None
) -> dict[str, Any]:
    """Plain placeholder data for the copy slots.

    Deliberately mundane. A demo value that looked like a real astrological
    claim would be a claim on a lock screen with no validator behind it, which
    is precisely what `service._render`'s header rules out.
    """
    return {
        "festival": "Raksha Bandhan",
        "occasion": "Raksha Bandhan",
        "note": "the 3pm call",
        "time": "11:20",
        "topic": "the lease decision",
        "graha": "Guru",
    }


def _as_wire(result) -> dict[str, Any]:  # noqa: ANN001
    return {
        "message_id": result.message_id,
        "sent": result.sent,
        "channels": [c.value for c in result.channels],
        "blocked": result.blocked.value if result.blocked else None,
        "halt_token": result.halt_token,
        # §32.6, named on the response. A demo can point at this field and say
        # "that is the brief going out inside her quiet hours, on purpose".
        "quiet_hours_exempt": result.quiet_hours_exempt,
        "failures": [
            {"channel": c.value, "failure": f.value} for c, f in result.failures
        ],
    }


__all__ = ["available_channels", "policy", "router"]
