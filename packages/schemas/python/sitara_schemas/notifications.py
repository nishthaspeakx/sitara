"""GENERATED FILE — do not edit. Source: packages/schemas/src/*.json (run scripts/generate.py).

SPEC §23 — the vocabulary of a notification.

`sitara_api.notifications` writes these onto `notifications`,
`push_subscriptions` and `notification_preferences` rows; S41 renders
the §23.5 category × channel matrix from them. Two of these sets were
already declared privately in `daily_guidance.notify` — this is the
package's rule applied at the moment the second declaration was about
to appear rather than after a screen had rendered the drift.

The RULES over these ids — which class bypasses quiet hours, which
trigger consumes the 1/day slot, what a dead subscription does to the
fallback ladder — belong to `sitara_api.notifications`, exactly as
§32.4's consent rules stay in `memory.taxonomy` and §22.13's clock
stays in `payments.lifecycle`. This file is the closed sets only.
"""

from enum import StrEnum

__all__ = [
    "BRIEF_DELIVERY_SLO_MINUTES",
    "BRIEF_DELIVERY_SLO_RATE",
    "BRIEF_EXPIRY_LOCAL_HOUR",
    "CONTEXTUAL_DAILY_CAP",
    "CONTEXTUAL_TRIGGERS",
    "CONTEXTUAL_TRIGGER_PRIORITY",
    "ContextualTrigger",
    "DAILY_CAP",
    "DEDUPE_WINDOW_HOURS",
    "DELIVERY_FAILURES",
    "DeliveryFailure",
    "EMERGENCY_STOP_SECONDS",
    "LANGUAGE_HEALTH_BAND",
    "MARKETING_WEEKLY_CAP",
    "MESSAGE_CLASSES",
    "MESSAGE_CLASS_LETTER",
    "MORNING_WAVE_ALARM_MINUTES",
    "MORNING_WAVE_DELIVERY_FLOOR",
    "MUHURAT_REMINDER_LEAD_HOURS",
    "MessageClass",
    "NIGHT_NUDGE_EXPIRY_LOCAL",
    "NOTIFICATION_CATEGORIES",
    "NOTIFICATION_CHANNELS",
    "NOTIFICATION_STATUSES",
    "NotificationCategory",
    "NotificationChannel",
    "NotificationStatus",
    "OPT_OUT_SPIKE_MULTIPLE",
    "OTP_EXPIRY_MINUTES",
    "PAUSE_EVERYTHING_DAYS",
    "PREFERENCE_APPLY_SECONDS",
    "PUSH_CONSECUTIVE_FAILURES_DEAD",
    "PUSH_SUBSCRIPTION_STATES",
    "PushSubscriptionState",
    "QUIET_HOURS_DEFAULT_END",
    "QUIET_HOURS_DEFAULT_START",
    "REENGAGEMENT_MAX_PER_WEEK",
    "REENGAGEMENT_QUIET_DAYS",
    "TRIGGER_AUTOPAUSE_OPEN_RATE",
    "TRIGGER_AUTOPAUSE_WINDOW_DAYS",
]


class MessageClass(StrEnum):
    """§23.1's four classes. 'behaviour differs by class — hard-coded, not configurable per template', which is why this is a closed set of four and not a template field. The ID is the wire format and the LETTER is §23's own label — the same split §4.3's presence ordinals and §32.4's memory numbering already use. Writing the letters as the ids would put `MessageClass.T` in every call site and make the one thing a reader most needs (is this the class that bypasses quiet hours?) a lookup rather than a word."""

    TRANSACTIONAL = "transactional"
    DAILY_LOOP = "daily_loop"
    CONTEXTUAL = "contextual"
    MARKETING = "marketing"


MESSAGE_CLASSES: tuple[MessageClass, ...] = (
    MessageClass.TRANSACTIONAL,
    MessageClass.DAILY_LOOP,
    MessageClass.CONTEXTUAL,
    MessageClass.MARKETING,
)


class NotificationChannel(StrEnum):
    """§23.3's three delivery surfaces. Deliberately NOT a provider list: `push` is the browser's own Push API over VAPID (§6.2), `email` is whichever SMTP host is configured, and `whatsapp` is a BSP — which of them answered is `notifications.providers.base.ChannelProviderName` and never crosses to a client. A channel is a thing a user toggles in §23.5's matrix; a provider is a thing operations swaps."""

    PUSH = "push"
    WHATSAPP = "whatsapp"
    EMAIL = "email"


NOTIFICATION_CHANNELS: tuple[NotificationChannel, ...] = (
    NotificationChannel.PUSH,
    NotificationChannel.WHATSAPP,
    NotificationChannel.EMAIL,
)


class NotificationCategory(StrEnum):
    """§23.5's five per-category toggles — the ROWS of the preference matrix, whose columns are `notification_channel`. Deliberately not the same set as `message_class`: a class is a behaviour the code hard-codes and a category is a choice the user makes, and the two differ in exactly the place that matters. §23.5 gives no toggle for Class T at all (an OTP is not something to opt out of), and it splits Class C into `contextual` and `festival` because a person who wants festival greetings and no transit nudges is an ordinary person rather than an edge case."""

    MORNING = "morning"
    NIGHT = "night"
    CONTEXTUAL = "contextual"
    FESTIVAL = "festival"
    MARKETING = "marketing"


NOTIFICATION_CATEGORIES: tuple[NotificationCategory, ...] = (
    NotificationCategory.MORNING,
    NotificationCategory.NIGHT,
    NotificationCategory.CONTEXTUAL,
    NotificationCategory.FESTIVAL,
    NotificationCategory.MARKETING,
)


class ContextualTrigger(StrEnum):
    """§23.2's catalogue, and it is CLOSED — 'Nothing else qualifies.' The ordinal is §23.2's own priority order, highest wins, ties broken by the user's engagement history. Trigger 1 is the odd one and its oddity is load-bearing: a user-requested reminder is Class T (user-initiated), so it neither respects quiet hours nor consumes the 1/day contextual slot, and modelling it anywhere but inside this catalogue would leave 'always wins' as a sentence nothing implements. Every send records its trigger id — that is what §23.2's auto-pause reads."""

    USER_REMINDER = "user_reminder"
    MUHURAT_WINDOW = "muhurat_window"
    FESTIVAL_OR_FAMILY = "festival_or_family"
    REFLECTION_FOLLOWUP = "reflection_followup"
    TRANSIT_CHANGE = "transit_change"
    QUIET_REENGAGEMENT = "quiet_reengagement"


CONTEXTUAL_TRIGGERS: tuple[ContextualTrigger, ...] = (
    ContextualTrigger.USER_REMINDER,
    ContextualTrigger.MUHURAT_WINDOW,
    ContextualTrigger.FESTIVAL_OR_FAMILY,
    ContextualTrigger.REFLECTION_FOLLOWUP,
    ContextualTrigger.TRANSIT_CHANGE,
    ContextualTrigger.QUIET_REENGAGEMENT,
)


class NotificationStatus(StrEnum):
    """§23.7's single source-of-truth lifecycle: 'status: queued → sent → delivered/failed/expired'. `superseded` is the sixth and is ours rather than the spec's — §23.4's collapse key requires that a regenerated brief REPLACE its push, and a replaced row is neither failed (nothing went wrong) nor expired (its time had not passed). Recording it as either would make §23.8's delivery analytics describe a defect that did not happen."""

    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


NOTIFICATION_STATUSES: tuple[NotificationStatus, ...] = (
    NotificationStatus.QUEUED,
    NotificationStatus.SENT,
    NotificationStatus.DELIVERED,
    NotificationStatus.FAILED,
    NotificationStatus.EXPIRED,
    NotificationStatus.SUPERSEDED,
)


class PushSubscriptionState(StrEnum):
    """§23.6's token lifecycle, as two states rather than a boolean, because the two die differently and the difference is what the ladder reads. There is no `expiring` member: §23.6 marks a 410/404 dead IMMEDIATELY and 3 consecutive failures dead, and a middle state would be a subscription the router kept trying while the push service had already told us it was gone."""

    ACTIVE = "active"
    DEAD = "dead"


PUSH_SUBSCRIPTION_STATES: tuple[PushSubscriptionState, ...] = (
    PushSubscriptionState.ACTIVE,
    PushSubscriptionState.DEAD,
)


class DeliveryFailure(StrEnum):
    """Why a channel did not take a message, NORMALISED — the same rule `payment_failure_reason` states, for the same reason: a push service's status line, an SMTP reply code and a BSP's error body are three vocabularies, and §2.4 would render any of them in the wrong language even where §13 permitted them in a log. The distinction that earns this enum is `subscription_gone` versus `transient`: §23.6 kills a subscription on the first of those and tolerates two of the second, so collapsing them would either kill live subscriptions on a flaky network or keep pushing at an endpoint the browser has already discarded."""

    SUBSCRIPTION_GONE = "subscription_gone"
    TRANSIENT = "transient"
    REJECTED = "rejected"
    UNCONFIGURED = "unconfigured"


DELIVERY_FAILURES: tuple[DeliveryFailure, ...] = (
    DeliveryFailure.SUBSCRIPTION_GONE,
    DeliveryFailure.TRANSIENT,
    DeliveryFailure.REJECTED,
    DeliveryFailure.UNCONFIGURED,
)


#: §23.1's own labels. Documentation, and the word an operator uses when
#: they say 'stop the D queue' — never the wire format. The IDs are the
#: wire format, for the reason §4.3's ordinals are not: a letter in every
#: call site makes the one question a reader has (does this class bypass
#: quiet hours?) a lookup rather than a word.
MESSAGE_CLASS_LETTER: dict[MessageClass, str] = {
    MessageClass.TRANSACTIONAL: "T",
    MessageClass.DAILY_LOOP: "D",
    MessageClass.CONTEXTUAL: "C",
    MessageClass.MARKETING: "M",
}

#: §23.2's catalogue in ITS OWN priority order — 'highest wins, tie-broken
#: by user's engagement history'. A tuple rather than an ordinal map
#: because the only thing anything does with this is walk it in order,
#: and a map would let a caller iterate a dict and get insertion order by
#: luck. The ordinals in the source JSON are checked against 1..6.
CONTEXTUAL_TRIGGER_PRIORITY: tuple[ContextualTrigger, ...] = (
    ContextualTrigger.USER_REMINDER,
    ContextualTrigger.MUHURAT_WINDOW,
    ContextualTrigger.FESTIVAL_OR_FAMILY,
    ContextualTrigger.REFLECTION_FOLLOWUP,
    ContextualTrigger.TRANSIT_CHANGE,
    ContextualTrigger.QUIET_REENGAGEMENT,
)


#: §23.1 / §23.9 — the 3/day cap Class T bypasses. §23.9 makes a cap breach release-blocking, so the number lives here rather than in the job that enforces it and the test that checks it.
DAILY_CAP = 3

#: §23.1 / §23.2 — 'Class C — Contextual (max 1/day)'. The slot §23.2's trigger 1 deliberately does not consume.
CONTEXTUAL_DAILY_CAP = 1

#: §23.1 — Class M is 'hard-capped 2/week'. A rolling seven days, not a calendar week: a calendar reset lets four land inside 48 hours across a Sunday.
MARKETING_WEEKLY_CAP = 2

#: §23.5 — 'quiet hours (default 22:30–07:00 local, user-adjustable)'. Zero-padded local HH:MM, the same string form §7.1's `brief_time` uses and for the same reason: these are compared as strings.
QUIET_HOURS_DEFAULT_START = '22:30'

#: §23.5 — the other end of the default window. It is BEFORE the start in string order, which is what makes the window wrap midnight; every comparison over it has to handle that and a test pins it.
QUIET_HOURS_DEFAULT_END = '07:00'

#: §23.5 — 'Changes apply within 60s (preferences cached in Redis with pub/sub invalidation)'. This is the cache TTL, which is the ceiling on the promise when the pub/sub message is lost; the invalidation is what makes the ordinary case instant.
PREFERENCE_APPLY_SECONDS = 60

#: §23.5 — 'one-tap "pause everything for a week" (Class T exempt, stated plainly)'.
PAUSE_EVERYTHING_DAYS = 7

#: §23.4 — 'morning brief push expires at 12:00 local (undelivered → dropped, not late-delivered; the brief itself is in-app regardless)'.
BRIEF_EXPIRY_LOCAL_HOUR = 12

#: §23.4 — 'night nudge expires at 23:30 local'. A time rather than an hour because 23:30 is not on an hour boundary and rounding it to 23:00 or 00:00 changes who gets a nudge.
NIGHT_NUDGE_EXPIRY_LOCAL = '23:30'

#: §23.4 — 'Class T never expires except OTP (10 min)'. The ONE exception to the one exception, which is why it is a named constant rather than a literal in the OTP sender.
OTP_EXPIRY_MINUTES = 10

#: §23.3 — 'cross-channel dedupe key `user+message_id` in Redis, 24h'. What stops the push→WhatsApp fallback from being a double send.
DEDUPE_WINDOW_HOURS = 24

#: §23.6 — '3 consecutive failures → dead'. Consecutive, so any success resets the counter; a cumulative count would retire a subscription that has worked a thousand times over a year of flaky mornings.
PUSH_CONSECUTIVE_FAILURES_DEAD = 3

#: §23.2(6) — '3+ quiet days' before a single re-engagement check-in becomes eligible.
REENGAGEMENT_QUIET_DAYS = 3

#: §23.2(6) — 'ONE gentle check-in per week maximum'. §29.2 is why there is no second.
REENGAGEMENT_MAX_PER_WEEK = 1

#: §23.2(2) — the muhurat window the user asked about is 'approaching (≤2h)'.
MUHURAT_REMINDER_LEAD_HOURS = 2

#: §23.2 — 'any trigger with open-rate <15% trailing 14 days is auto-paused and flagged'. Strictly below: a trigger sitting exactly at 15% is not paused.
TRIGGER_AUTOPAUSE_OPEN_RATE = 0.15

#: §23.2 — the trailing window the open rate is measured over.
TRIGGER_AUTOPAUSE_WINDOW_DAYS = 14

#: §23.8 — 'opt-out spike >2× baseline on any template (auto-pauses that template, flags admin)'.
OPT_OUT_SPIKE_MULTIPLE = 2

#: §23.8 — 'morning-wave delivery <97% by +15 min (pages on-call)'.
MORNING_WAVE_DELIVERY_FLOOR = 0.97

#: §23.8 — the '+15 min' the delivery floor is measured at.
MORNING_WAVE_ALARM_MINUTES = 15

#: §23.8 — 'SLO: 95% of morning briefs delivered within 5 min of target time'. This is the number the §23.9 timezone matrix asserts against, which is what makes 'the brief arrives at brief_time' a measurement rather than a claim.
BRIEF_DELIVERY_SLO_MINUTES = 5

#: §23.8 — the 95% of that SLO.
BRIEF_DELIVERY_SLO_RATE = 0.95

#: §23.7 — 'Emergency stop (§12) halts queues per class/channel/locale in <30s and is drill-tested'. The number the drill measures against.
EMERGENCY_STOP_SECONDS = 30

#: §23.8 — 'a language whose notification open rates sit outside the ±20% band gets the same named-owner treatment as any other per-language metric' (§18).
LANGUAGE_HEALTH_BAND = 0.2
