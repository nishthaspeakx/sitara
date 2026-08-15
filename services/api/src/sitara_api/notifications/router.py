"""§23.5's preference centre and §23.6's push registration, over HTTP.

    GET    /v1/notifications/preferences        S41's whole state
    PUT    /v1/notifications/preferences        the matrix, hours, brief time
    POST   /v1/notifications/preferences/pause  §23.5's one week
    DELETE /v1/notifications/preferences/pause  §29.2 — un-pausing is one tap
    POST   /v1/notifications/preferences/overlap-ack   §32.6's "once"
    GET    /v1/notifications/push/key           the VAPID public key
    POST   /v1/notifications/push               register a browser (§23.6)
    DELETE /v1/notifications/push               the browser is going away
    POST   /v1/notifications/{message_id}/opened   §23.8's open rate

── Two shapes worth explaining ─────────────────────────────────────────────

**The matrix crosses the wire as a list of triples, not a nested object.** A
nested `{category: {channel: bool}}` makes a missing CHANNEL and a missing
CATEGORY two different absences for the client to handle, and S41 renders a
grid where every cell exists. A flat list of `{category, channel, enabled}` has
exactly one absence, and the server fills the rest from the declared defaults.

**`available` is served per channel and is NOT the same as `enabled`.** §23.3's
WhatsApp cell is DECLARED, so S41 must render its column as a real column that
is switched on or off by the user AND labelled unavailable — her preference is
kept and honoured on the day the cell flips. A client that inferred
availability from the toggle would silently discard the preference of everyone
who set it early.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sitara_schemas import ErrorCode
from sitara_schemas.notifications import (
    NOTIFICATION_CATEGORIES,
    NOTIFICATION_CHANNELS,
    PAUSE_EVERYTHING_DAYS,
    NotificationCategory,
    NotificationChannel,
)

from sitara_api.auth.router import CurrentSession
from sitara_api.errors import ApiError
from sitara_api.notifications.preferences import Preferences
from sitara_api.notifications.providers.base import PushSubscription
from sitara_api.notifications.providers.registry import vapid_path
from sitara_api.notifications.providers.routing import available_channels, resolve
from sitara_api.notifications.providers.webpush import VapidKeypair
from sitara_api.notifications.quiet_hours import QuietHours
from sitara_api.notifications.store import (
    NotificationStore,
    PreferenceStore,
    PushSubscriptionStore,
)

router = APIRouter(prefix="/v1/notifications", tags=["notifications"])


class MatrixCell(BaseModel):
    category: NotificationCategory
    channel: NotificationChannel
    enabled: bool


class ChannelView(BaseModel):
    """One column of S41's grid."""

    channel: NotificationChannel
    #: §23.3's capability matrix, not the user's choice. False for WhatsApp
    #: today; the toggle still renders and is still stored.
    available: bool
    #: A message KEY (§2.4) explaining an unavailable column, or None.
    reason_key: str | None = None


class PreferencesView(BaseModel):
    """Everything S41 renders."""

    matrix: list[MatrixCell]
    channels: list[ChannelView]
    categories: list[NotificationCategory]
    quiet_hours_start: str
    quiet_hours_end: str
    brief_time: str
    paused_until: dt.datetime | None = None
    pause_days: int = PAUSE_EVERYTHING_DAYS
    follow_timezone: bool = True
    home_timezone: str = "Asia/Kolkata"
    #: §32.6 — set when the brief lands inside quiet hours AND she has not
    #: acknowledged THIS overlap. Null once acknowledged, and non-null again if
    #: she later creates a different one.
    overlap_to_flag: str | None = None

    @classmethod
    def of(cls, preferences: Preferences) -> PreferencesView:
        return cls(
            matrix=[
                MatrixCell(
                    category=category,
                    channel=channel,
                    enabled=preferences.allows(category, channel),
                )
                for category in NOTIFICATION_CATEGORIES
                for channel in NOTIFICATION_CHANNELS
            ],
            channels=[
                ChannelView(
                    channel=channel,
                    available=resolve(channel).available,
                    reason_key=resolve(channel).reason_key,
                )
                for channel in NOTIFICATION_CHANNELS
            ],
            categories=list(NOTIFICATION_CATEGORIES),
            quiet_hours_start=preferences.quiet_hours.start,
            quiet_hours_end=preferences.quiet_hours.end,
            brief_time=preferences.brief_time,
            paused_until=preferences.paused_until,
            follow_timezone=preferences.follow_timezone,
            home_timezone=preferences.home_timezone,
            overlap_to_flag=preferences.overlap_to_flag(),
        )


class PreferencesUpdate(BaseModel):
    """A partial update. Every field optional — S41 saves one control at a time
    (§29.2's no-dark-patterns posture applied to a settings screen: nothing
    here is a form you have to complete before anything takes effect)."""

    matrix: list[MatrixCell] | None = None
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    brief_time: str | None = None
    follow_timezone: bool | None = None
    home_timezone: str | None = None


class PushRegistration(BaseModel):
    """Exactly what `PushSubscription.toJSON()` gives the client."""

    endpoint: str
    p256dh: str
    auth: str
    user_agent: str | None = Field(default=None, max_length=400)


class PushUnregister(BaseModel):
    endpoint: str


def _preferences(request: Request) -> PreferenceStore:
    return PreferenceStore(request.app.state.db, getattr(request.app.state, "redis", None))


def _subscriptions(request: Request) -> PushSubscriptionStore:
    return PushSubscriptionStore(request.app.state.db)


@router.get("/preferences", response_model=PreferencesView)
async def read_preferences(request: Request, session: CurrentSession) -> PreferencesView:
    user_id, _ = session
    return PreferencesView.of(await _preferences(request).load(str(user_id)))


@router.put("/preferences", response_model=PreferencesView)
async def update_preferences(
    body: PreferencesUpdate, request: Request, session: CurrentSession
) -> PreferencesView:
    """§23.5's changes, applied within 60s by `PreferenceStore.save`."""
    user_id, _ = session
    store = _preferences(request)
    preferences = await store.load(str(user_id))

    if body.matrix is not None:
        preferences = preferences.with_matrix(
            (cell.category, cell.channel, cell.enabled) for cell in body.matrix
        )
    if body.quiet_hours_start is not None or body.quiet_hours_end is not None:
        try:
            preferences = preferences.with_quiet_hours(
                QuietHours(
                    start=body.quiet_hours_start or preferences.quiet_hours.start,
                    end=body.quiet_hours_end or preferences.quiet_hours.end,
                )
            )
        except ValueError as exc:
            raise ApiError(
                ErrorCode.SYS_VALIDATION, "errors.sys.validation"
            ) from exc
    if body.brief_time is not None:
        if not _is_local_time(body.brief_time):
            # Zero-padded, always. §7.1's wave index does a STRING range scan
            # over `brief_time`, so an unpadded "7:00" sorts after "10:00" and
            # the user is selected into the wrong tick — a brief that arrives
            # at the wrong hour with nothing in any log to say why.
            raise ApiError(ErrorCode.SYS_VALIDATION, "errors.sys.validation")
        preferences = preferences.with_brief_time(body.brief_time)
    if body.follow_timezone is not None:
        preferences = _replace(preferences, follow_timezone=body.follow_timezone)
    if body.home_timezone is not None:
        preferences = _replace(preferences, home_timezone=body.home_timezone)

    await store.save(preferences, now=dt.datetime.now(dt.UTC))
    return PreferencesView.of(preferences)


@router.post("/preferences/pause", response_model=PreferencesView)
async def pause(request: Request, session: CurrentSession) -> PreferencesView:
    """§23.5's "pause everything for a week" (Class T exempt, stated plainly)."""
    user_id, _ = session
    store = _preferences(request)
    now = dt.datetime.now(dt.UTC)
    preferences = (await store.load(str(user_id))).paused_for_a_week(now)
    await store.save(preferences, now=now)
    return PreferencesView.of(preferences)


@router.delete("/preferences/pause", response_model=PreferencesView)
async def resume(request: Request, session: CurrentSession) -> PreferencesView:
    """§29.2: the close is always available. One tap, no confirmation, no
    minimum — a pause you have to justify ending is a dark pattern."""
    user_id, _ = session
    store = _preferences(request)
    now = dt.datetime.now(dt.UTC)
    preferences = (await store.load(str(user_id))).resumed()
    await store.save(preferences, now=now)
    return PreferencesView.of(preferences)


@router.post("/preferences/overlap-ack", response_model=PreferencesView)
async def acknowledge_overlap(
    request: Request, session: CurrentSession
) -> PreferencesView:
    """§32.6's "flags the overlap once" — this is the once being spent.

    It records the FINGERPRINT of the overlap she saw, not a boolean, so a
    later overlap she has never seen flags again. §32.6 also forbids silently
    suppressing the brief, and nothing here can: acknowledging changes what the
    screen says and never what the sender does.
    """
    user_id, _ = session
    store = _preferences(request)
    now = dt.datetime.now(dt.UTC)
    preferences = (await store.load(str(user_id))).acknowledging_overlap()
    await store.save(preferences, now=now)
    return PreferencesView.of(preferences)


@router.get("/push/key")
async def push_key(request: Request) -> dict[str, str | None]:
    """The VAPID public key, for `pushManager.subscribe` (§6.2).

    Deliberately UNAUTHENTICATED and deliberately safe: it is the application
    server's public key, RFC 8292 expects every client to hold it, and knowing
    it lets nobody send anything — a push is signed by the private half and
    encrypted to keys only the browser has.

    Returns null rather than 404 when no keypair is configured, so the client
    can skip the subscribe prompt instead of rendering an error for a channel
    §23.3's ladder is already routing around.
    """
    settings = request.app.state.settings
    path = vapid_path(settings)
    if path is None or not path.exists():
        return {"public_key": None}
    return {"public_key": VapidKeypair.load(path).public_key_b64}


@router.post("/push", status_code=201)
async def register_push(
    body: PushRegistration, request: Request, session: CurrentSession
) -> dict[str, bool]:
    """§23.6's per-device registration, and its silent re-subscribe.

    An upsert on the endpoint, so calling this on every app open — which is
    what §23.6's "silent re-subscribe attempt on next app open" amounts to — is
    idempotent rather than a row per launch.
    """
    user_id, _ = session
    if NotificationChannel.PUSH not in available_channels():
        raise ApiError(ErrorCode.SYS_UNAVAILABLE, "notifications.channel_unavailable")
    await _subscriptions(request).upsert(
        user_id=str(user_id),
        subscription=PushSubscription(
            endpoint=body.endpoint, p256dh=body.p256dh, auth=body.auth
        ),
        user_agent=body.user_agent,
        now=dt.datetime.now(dt.UTC),
    )
    return {"registered": True}


@router.delete("/push")
async def unregister_push(
    body: PushUnregister, request: Request, session: CurrentSession
) -> dict[str, int]:
    """The browser told us it is going away.

    A DELETE, unlike §23.6's dead-marking: we concluded a subscription was
    gone in that case, and here the client said so. The difference matters
    because a dead row drives a re-subscribe prompt and a removed one does not
    — offering to re-enable push to somebody who just turned it off is exactly
    the nagging §29.2 forbids.
    """
    user_id, _ = session
    removed = await _subscriptions(request).remove(
        user_id=str(user_id), endpoint=body.endpoint
    )
    return {"removed": removed}


@router.post("/{message_id}/opened", status_code=204)
async def mark_opened(
    message_id: str, request: Request, session: CurrentSession
) -> None:
    """§23.8's open rate, and §23.2's auto-pause input.

    Scoped to the caller's own id, so one user cannot mark another's
    notification opened — which would be a way to keep a trigger above §23.2's
    15% threshold from outside.
    """
    user_id, _ = session
    await NotificationStore(request.app.state.db).mark_opened(
        user_id=str(user_id), message_id=message_id, now=dt.datetime.now(dt.UTC)
    )


def _replace(preferences: Preferences, **changes: object) -> Preferences:
    from dataclasses import replace

    return replace(preferences, **changes)  # type: ignore[arg-type]


def _is_local_time(value: str) -> bool:
    return (
        len(value) == 5
        and value[2] == ":"
        and value[:2].isdigit()
        and value[3:].isdigit()
        and int(value[:2]) < 24
        and int(value[3:]) < 60
    )
