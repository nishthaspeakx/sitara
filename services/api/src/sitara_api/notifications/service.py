"""The send pipeline (§23.1–§23.7). One message in, one ledger row out.

Every rule in §23 that can stop a message is applied here, in this order, and
the ORDER is the design. Each gate answers a different question and putting one
of them later would either send something it should have stopped or spend
something it should not have.

    1  §23.7  emergency stop      is this queue halted right now?
    2  §23.5  the pause           has she paused everything for a week?
    3  §23.1  quiet hours         may this class speak at this local hour?
       §32.6                      …unless this is the brief appointment
    4  §23.1  the caps            3/day · 1/day contextual · 2/week marketing
    5  §23.4  the ledger row      written BEFORE anything leaves
    6  §23.3  the dedupe claim    has some rung already taken this message?
    7  §23.3  the ladder          which channels, and in which shape
    8  §23.6  the token lifecycle what each outcome means for the subscription

── Why the order is what it is ─────────────────────────────────────────────

**The halt is first** because it is an operator saying "stop" during an
incident, and a message that got past it because it was already inside the
pipeline is exactly the message the halt existed to catch. It is also the
cheapest check.

**Quiet hours come before the caps**, and the reverse would be a real bug: a
message held by quiet hours has not been sent, so it must not consume one of
the day's three. Counting first would let three held messages exhaust a cap
that nothing ever used, and the user would receive nothing all day while the
ledger said she had received her limit.

**The ledger row is written before delivery, not after.** `notify.py` states
the general form of this rule for the morning brief and the reason is the same
here: a row written after a successful send is a row that does not exist if the
process dies in between — and the retry then has no record, no idempotency key
collision and nothing stopping a second delivery. §23.9 makes a duplicate
delivery release-blocking, so the worst case has to be a message that was sent
and recorded as queued, never the reverse.

That is the trade this pipeline makes explicitly. If a worker dies between a
successful push and `mark_sent`, the dedupe claim is still held, so the retry
does NOT send again — and the row stays `queued` until the expiry sweep retires
it. The result is one delivery and a mislabelled row. §23.8's delivery rate is
slightly pessimistic; nobody is messaged twice. An unsent message can be sent
later; a sent one cannot be unsent.

── What this service deliberately does not do ──────────────────────────────

**It does not render astrology.** A notification body is composed from copy in
the catalogs plus values the caller passes. Nothing here reads a fact, and no
notification makes an astrological claim — §5.3's cite-or-die has no reach into
a system notification, so the honest design is that a push says "your brief is
ready" and the CLAIM lives on the Today screen behind the deep link, where the
validator runs.

**It does not know which channel answered.** `ladder.build` chooses, the
adapters carry, and this file records. That is what makes landing WhatsApp one
capability cell plus an adapter.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo

from sitara_schemas.notifications import (
    DAILY_CAP,
    ContextualTrigger,
    DeliveryFailure,
    MessageClass,
    NotificationCategory,
    NotificationChannel,
    NotificationStatus,
)

from sitara_api.localisation import MissingString, resolve
from sitara_api.notifications import templates
from sitara_api.notifications.catalogue import CATALOGUE
from sitara_api.notifications.classes import CLASS_FOR_CATEGORY, policy
from sitara_api.notifications.emergency_stop import EmergencyStop
from sitara_api.notifications.ladder import Dedupe, DeliveryMode
from sitara_api.notifications.ladder import build as build_ladder
from sitara_api.notifications.lifecycle import record_failure, record_success
from sitara_api.notifications.preferences import Preferences
from sitara_api.notifications.providers.base import (
    ChannelProviderName,
    ChannelUnavailable,
    Delivery,
    DeliveryOutcome,
    NotificationChannelAdapter,
    Recipient,
)
from sitara_api.notifications.quiet_hours import (
    appointment_local_time,
    local_time_of,
    may_send,
)
from sitara_api.notifications.store import (
    NotificationStore,
    PreferenceStore,
    PushSubscriptionStore,
    local_day_bounds,
    marketing_window_start,
)

logger = logging.getLogger(__name__)


class Blocked(StrEnum):
    """Why a message did not go. Every member is a §23 rule, named.

    Recorded rather than collapsed into a boolean because the reasons need
    different things from different people: `QUIET_HOURS` is the user's own
    setting working, `HALTED` is an incident, `CAP_REACHED` is §23.1 protecting
    her, and `UNREACHABLE` is a prompt to add an address. A single "not sent"
    would send all four to the same unhelpful place, and §23.8's dashboards
    could not tell a working product from a broken one.
    """

    HALTED = "halted"
    PAUSED = "paused"
    QUIET_HOURS = "quiet_hours"
    CAP_REACHED = "cap_reached"
    CONTEXTUAL_SLOT_SPENT = "contextual_slot_spent"
    MARKETING_CAP_REACHED = "marketing_cap_reached"
    NO_CONSENT = "no_consent"
    UNREACHABLE = "unreachable"
    ALREADY_SENT = "already_sent"
    EXPIRED = "expired"


@dataclass(frozen=True)
class SendRequest:
    """One message somebody wants to send.

    `category` is the §23.5 toggle and the CLASS is derived from it — a caller
    cannot choose its own class, which is what stops a marketing message being
    posted as Class T to get past quiet hours and the cap. §23.1 hard-codes
    behaviour per class precisely so that this is not a per-message decision.
    """

    user_id: str
    category: NotificationCategory
    locale: str
    timezone: str
    #: §23.4's idempotency identity. DERIVED by the caller from what is being
    #: announced — never random — so a retried enqueue computes the same id and
    #: collides rather than sending twice.
    message_id: str
    #: The values the copy interpolates. Plain data (a name, a city, a time),
    #: never a rendered sentence and never an astrological claim.
    params: Mapping[str, Any] = field(default_factory=dict)
    trigger: ContextualTrigger | None = None
    collapse_key: str | None = None
    scheduled_at: dt.datetime | None = None
    expires_at: dt.datetime | None = None
    #: §23.3's per-purpose exclusions — `ladder.OTP_EXCLUDED_CHANNELS` is the
    #: one this milestone has.
    excludes: frozenset[NotificationChannel] = frozenset()

    @property
    def message_class(self) -> MessageClass:
        if self.trigger is not None:
            # §23.2(1)'s reminder is Class T through the catalogue, not through
            # its category — which is the whole reason it neither waits for
            # quiet hours nor spends the contextual slot.
            return CATALOGUE[self.trigger].message_class
        return CLASS_FOR_CATEGORY[self.category]


@dataclass(frozen=True)
class SendResult:
    """What happened, in enough detail for §23.8 and for a demo to show it."""

    message_id: str
    sent: bool
    channels: tuple[NotificationChannel, ...] = ()
    blocked: Blocked | None = None
    #: Set when §23.7 held it — which halt, so an incident reads "held by
    #: channel:push" rather than "held".
    halt_token: str | None = None
    #: §32.6's exemption, when it was used. Surfaced so the demo and the
    #: acceptance harness can assert the brief went out INSIDE quiet hours
    #: because of the appointment, rather than because quiet hours failed.
    quiet_hours_exempt: bool = False
    failures: tuple[tuple[NotificationChannel, DeliveryFailure], ...] = ()


class NotificationService:
    """§23's send path. One instance per process; holds no per-user state."""

    def __init__(
        self,
        *,
        store: NotificationStore,
        preferences: PreferenceStore,
        subscriptions: PushSubscriptionStore,
        adapters: Mapping[NotificationChannel, NotificationChannelAdapter],
        dedupe: Dedupe,
        emergency_stop: EmergencyStop,
        recipients: RecipientResolver,
    ) -> None:
        self._store = store
        self._preferences = preferences
        self._subscriptions = subscriptions
        self._adapters = dict(adapters)
        self._dedupe = dedupe
        self._halt = emergency_stop
        self._recipients = recipients

    async def send(self, request: SendRequest, *, now: dt.datetime) -> SendResult:
        """Run §23's gates and, if they all pass, deliver."""
        message_class = request.message_class
        rules = policy(message_class)
        scheduled_at = request.scheduled_at or now
        expires_at = request.expires_at or (now + dt.timedelta(hours=12))

        # ---- 1. §23.7's emergency stop -----------------------------------
        halt_token = await self._halt.halted(
            message_class=message_class, channel=None, locale=request.locale
        )
        if halt_token:
            return SendResult(
                request.message_id, sent=False, blocked=Blocked.HALTED, halt_token=halt_token
            )

        # ---- 2. §23.4's expiry, before any work --------------------------
        if expires_at <= now:
            # "undelivered → dropped, not late-delivered". A message that
            # arrives at the sender already expired is the same case as one the
            # sweep finds, and answering it here saves the ledger a row that
            # would be written only to be retired in the same second.
            return SendResult(request.message_id, sent=False, blocked=Blocked.EXPIRED)

        preferences = await self._preferences.load(request.user_id)

        # ---- 3. §23.5's pause (Class T exempt) ---------------------------
        if rules.suppressible and preferences.is_paused(now):
            return SendResult(request.message_id, sent=False, blocked=Blocked.PAUSED)

        # ---- 4. §23.1 quiet hours + §32.6's one exception ----------------
        local_time = local_time_of(scheduled_at, request.timezone)
        verdict = may_send(
            category=request.category,
            local_time=local_time,
            quiet_hours=preferences.quiet_hours,
            # RESOLVED for this date, not the raw setting. On a spring-forward
            # morning §7.1 schedules a 02:30 brief for 03:00 — because 02:30
            # does not happen — and comparing against the string would hold the
            # brief in quiet hours and lose it. See `appointment_local_time`.
            brief_time=appointment_local_time(
                preferences.brief_time,
                scheduled_at.astimezone(ZoneInfo(request.timezone)).date().isoformat(),
                request.timezone,
            ),
        )
        if not verdict.allowed:
            return SendResult(request.message_id, sent=False, blocked=Blocked.QUIET_HOURS)

        # ---- 5. §23.1's caps ---------------------------------------------
        blocked = await self._capped(
            request, message_class=message_class, scheduled_at=scheduled_at, now=now
        )
        if blocked is not None:
            return SendResult(request.message_id, sent=False, blocked=blocked)

        # ---- 6. §23.3's ladder -------------------------------------------
        recipient = await self._recipients.resolve(request.user_id)
        ladder = build_ladder(
            category=request.category,
            preferences=preferences,
            recipient=recipient,
            excludes=request.excludes,
            # PASSED, never re-derived. §23.2(1)'s reminder is delivered under
            # the contextual category and is Class T, so a ladder that worked
            # the class out from the category gives it the daily loop's
            # first-success mode instead of §23.3's transactional fan-out.
            message_class=message_class,
        )
        if not ladder.deliverable:
            # Recorded as a FAILED row rather than dropped silently: §23.8's
            # dead-token and delivery-rate reporting is how "nobody in this
            # cohort can be reached" becomes visible, and a message that was
            # never written cannot appear in it.
            await self._store.record(
                user_id=request.user_id,
                message_id=request.message_id,
                message_class=message_class,
                category=request.category,
                channel=NotificationChannel.PUSH,
                locale=request.locale,
                template_id=self._template(request).template_id,
                template_version=templates.TEMPLATE_VERSION,
                scheduled_at=scheduled_at,
                expires_at=expires_at,
                collapse_key=request.collapse_key,
                trigger_id=request.trigger,
                status=NotificationStatus.FAILED,
            )
            return SendResult(
                request.message_id,
                sent=False,
                blocked=(
                    Blocked.NO_CONSENT
                    if ladder.reason_key == "notifications.all_channels_off"
                    else Blocked.UNREACHABLE
                ),
            )

        # ---- 7. §23.4's ledger row, BEFORE anything leaves ---------------
        await self._store.record(
            user_id=request.user_id,
            message_id=request.message_id,
            message_class=message_class,
            category=request.category,
            channel=ladder.channels[0],
            locale=request.locale,
            template_id=self._template(request).template_id,
            template_version=templates.TEMPLATE_VERSION,
            scheduled_at=scheduled_at,
            expires_at=expires_at,
            collapse_key=request.collapse_key,
            trigger_id=request.trigger,
        )

        # ---- 8. §23.3's cross-channel dedupe -----------------------------
        if not await self._dedupe.claim(request.user_id, request.message_id):
            # Someone — another worker, an earlier retry — already took this
            # message down the ladder. "NOT both" (§23.3), across processes.
            return SendResult(
                request.message_id, sent=False, blocked=Blocked.ALREADY_SENT
            )

        delivery_base = self._render(request, expires_at=expires_at)
        outcomes = await self._deliver(
            ladder.mode, ladder.channels, delivery_base, recipient, request, now=now
        )

        accepted = [c for c, o in outcomes if o.accepted]
        failures = tuple((c, o.failure) for c, o in outcomes if o.failure is not None)

        if not accepted:
            # Give the claim back — the key exists to stop a SECOND delivery,
            # not to stop a first one from ever happening.
            await self._dedupe.release(request.user_id, request.message_id)
            await self._store.mark_failed(
                user_id=request.user_id,
                message_id=request.message_id,
                failure=failures[0][1] if failures else DeliveryFailure.TRANSIENT,
                now=now,
            )
            return SendResult(
                request.message_id,
                sent=False,
                blocked=Blocked.UNREACHABLE,
                failures=failures,
                quiet_hours_exempt=verdict.exempt,
            )

        first = next(o for c, o in outcomes if o.accepted)
        await self._store.mark_sent(
            user_id=request.user_id,
            message_id=request.message_id,
            channel=accepted[0],
            provider_message_id=first.provider_message_id,
            now=now,
        )
        return SendResult(
            request.message_id,
            sent=True,
            channels=tuple(accepted),
            failures=failures,
            quiet_hours_exempt=verdict.exempt,
        )

    # -- the gates -------------------------------------------------------

    async def _capped(
        self,
        request: SendRequest,
        *,
        message_class: MessageClass,
        scheduled_at: dt.datetime,
        now: dt.datetime,
    ) -> Blocked | None:
        """§23.1's three caps, over the user's OWN day and week."""
        rules = policy(message_class)
        if rules.bypasses_daily_cap:
            # §23.1's Class T. Deliberately returns before any query — the cap
            # does not merely not apply, it is not consulted, so an OTP cannot
            # be delayed by a slow count.
            return None

        local_date = (
            scheduled_at.astimezone(ZoneInfo(request.timezone)).date().isoformat()
        )
        day_start, day_end = local_day_bounds(local_date, request.timezone)

        if message_class is MessageClass.CONTEXTUAL and await self._store.contextual_slot_spent(
            user_id=request.user_id, day_start=day_start, day_end=day_end
        ):
            return Blocked.CONTEXTUAL_SLOT_SPENT

        if rules.weekly_cap is not None:
            spent = await self._store.count_class_since(
                user_id=request.user_id,
                message_class=message_class,
                since=marketing_window_start(now),
            )
            if spent >= rules.weekly_cap:
                return Blocked.MARKETING_CAP_REACHED

        sent_today = await self._store.count_today(
            user_id=request.user_id, day_start=day_start, day_end=day_end
        )
        if sent_today >= DAILY_CAP:
            return Blocked.CAP_REACHED
        return None

    # -- delivery --------------------------------------------------------

    async def _deliver(
        self,
        mode: DeliveryMode,
        channels: Sequence[NotificationChannel],
        base: Delivery,
        recipient: Recipient,
        request: SendRequest,
        *,
        now: dt.datetime,
    ) -> list[tuple[NotificationChannel, DeliveryOutcome]]:
        """§23.3's three shapes. The difference between them is the section."""
        if mode is DeliveryMode.FIRST_SUCCESS:
            outcomes: list[tuple[NotificationChannel, DeliveryOutcome]] = []
            for channel in channels:
                outcome = await self._one(channel, base, recipient, request, now=now)
                outcomes.append((channel, outcome))
                if outcome.accepted:
                    # §23.3: "same message, NOT both". The loop stops here and
                    # that stop IS the rule.
                    break
            return outcomes

        # FANOUT and CONSENTED_ONLY both send on every rung; they differ in
        # what put the rungs there, which `ladder.build` has already settled.
        # Concurrently, because §23.3's transactional redundancy exists for
        # messages somebody is waiting on — an OTP that went to email first and
        # WhatsApp two seconds later is an OTP that arrived late twice.
        results = await asyncio.gather(
            *(self._one(c, base, recipient, request, now=now) for c in channels)
        )
        return list(zip(channels, results, strict=True))

    async def _one(
        self,
        channel: NotificationChannel,
        base: Delivery,
        recipient: Recipient,
        request: SendRequest,
        *,
        now: dt.datetime,
    ) -> DeliveryOutcome:
        """One rung, plus §23.6's consequence for the token."""
        adapter = self._adapters.get(channel)
        if adapter is None:
            # A channel the ladder admitted and this process has no adapter
            # for. `routing.available_channels` should have excluded it, so
            # this is a wiring mistake rather than a state — reported as its
            # own failure so it does not read as a delivery problem in §23.8.
            logger.error(
                "ladder admitted a channel with no adapter in this process",
                extra={"channel": channel.value},
            )
            return DeliveryOutcome(
                accepted=False,
                provider=ChannelProviderName.SMTP,
                failure=DeliveryFailure.UNCONFIGURED,
            )

        delivery = replace(base, channel=channel, recipient=recipient)
        try:
            outcome = await adapter.send(delivery)
        except ChannelUnavailable:
            outcome = DeliveryOutcome(
                accepted=False, provider=adapter.name, failure=DeliveryFailure.TRANSIENT
            )

        if channel is NotificationChannel.PUSH:
            await self._apply_token_lifecycle(request.user_id, recipient, outcome, now=now)
        return outcome

    async def _apply_token_lifecycle(
        self,
        user_id: str,
        recipient: Recipient,
        outcome: DeliveryOutcome,
        *,
        now: dt.datetime,
    ) -> None:
        """§23.6, applied to the subscription this send actually used.

        Looked up by ENDPOINT and not "the user's subscription": §23.6 is per
        device, and a laptop's 410 must not retire the phone that is working.
        """
        subscription = recipient.push_subscription
        if subscription is None:
            return
        records = await self._subscriptions.all_for(user_id)
        record = next(
            (r for r in records if r.subscription.endpoint == subscription.endpoint),
            None,
        )
        if record is None:
            return
        updated = (
            record_success(record, now=now)
            if outcome.accepted
            else record_failure(record, outcome.failure or DeliveryFailure.TRANSIENT, now=now)
        )
        if updated != record:
            await self._subscriptions.save(user_id, updated, now=now)

    # -- rendering -------------------------------------------------------

    def _template(self, request: SendRequest) -> templates.MessageTemplate:
        if request.trigger is not None:
            return templates.for_trigger(request.trigger)
        return templates.for_category(request.category)

    def _render(self, request: SendRequest, *, expires_at: dt.datetime) -> Delivery:
        """Copy in the user's own language (§2.4), or nothing at all.

        `MissingString` is allowed to propagate. §2.4 admits no English
        fallback, so the alternatives to raising are an English push on a Hindi
        lock screen or a notification with a raw key in it, and both are worse
        than a message that did not go out — the brief is on the Today screen
        either way, which is what §23.4 already says about a dropped push.
        `verify_catalogs` makes this a boot failure rather than a 07:00 one.
        """
        template = self._template(request)
        try:
            title = resolve(template.title_key, request.locale, **request.params)
            body = resolve(template.body_key, request.locale, **request.params)
        except MissingString:
            logger.error(
                "notification copy missing — refusing to send in the wrong language",
                extra={"locale": request.locale, "template": template.template_id},
            )
            raise

        rules = policy(request.message_class)
        return Delivery(
            message_id=request.message_id,
            message_class=request.message_class,
            channel=NotificationChannel.PUSH,  # replaced per rung
            recipient=Recipient(),  # replaced per rung
            locale=request.locale,
            title=title,
            body=body,
            deep_link=template.deep_link,
            expires_at=expires_at,
            collapse_key=request.collapse_key,
            # §23.3 — List-Unsubscribe on Class M, never Class T. Read from the
            # class table, so an adapter never decides it and a caller cannot.
            unsubscribe_url=(
                f"/api/v1/notifications/unsubscribe/{request.message_id}"
                if rules.unsubscribe_header
                else None
            ),
        )


class RecipientResolver:
    """Where this user can be reached (§23.3), from her own records.

    A class rather than a function because it holds the two stores, and a
    separate name because of the rule `providers/base.py` states: the SERVICE
    resolves a destination from the user's own row, and no request body has
    ever been able to supply one. Keeping that in a named seam is what makes it
    checkable — `test_no_caller_supplied_destination` reads this signature.
    """

    def __init__(self, db, subscriptions: PushSubscriptionStore) -> None:  # noqa: ANN001
        self._db = db
        self._subscriptions = subscriptions

    async def resolve(self, user_id: str) -> Recipient:
        from sitara_api.chat_orchestration.store import to_object_id

        row = await self._db.users.find_one(
            {"_id": to_object_id(user_id, field_name="users._id")}
        ) or {}
        live = await self._subscriptions.live_for(user_id)
        return Recipient(
            # The most recently successful device — `live_for` sorts by it, and
            # it is the best available proxy for the browser she is holding.
            push_subscription=live[0].subscription if live else None,
            email=row.get("email"),
            phone_e164=row.get("phone"),
            # §23.3's Meta-compliant opt-in, recorded in `consents`. A phone
            # number alone is never enough, and having the number is exactly
            # what makes that mistake easy.
            whatsapp_opted_in=bool(row.get("whatsapp_opted_in")),
        )


def preferences_for_tests(user_id: str) -> Preferences:
    """§23.5's declared defaults, as a value. Used by the acceptance harness so
    it asserts against the DECLARED defaults rather than against whatever a
    developer's database happens to hold — the lesson `Settings()` taught."""
    return Preferences(user_id=user_id)
