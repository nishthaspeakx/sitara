"""§23.2's contextual catalogue — the six triggers, and who gets the 1/day slot.

§23.2 is a closed list and says so: "Nothing else qualifies." The set lives in
`sitara_schemas.notifications`; what lives here is the part that is a RULE —
priority, the slot, the TTLs, and the auto-pause.

── The slot, and the trigger that does not take it ─────────────────────────

§23.1 caps Class C at one message a day. §23.2 orders six triggers and awards
that one slot to the highest-priority eligible candidate. Trigger 1 is the
exception and it is the reason this module cannot be a `max()`:

    "(1) user-requested reminder ('remind me before the 3pm call') — always
     wins, and does NOT consume the contextual slot (it is Class T,
     user-initiated)"

A reminder the user asked for is not a message we decided to send. It is not
competing with the festival greeting, it does not use up the day's one
contextual message, and — being Class T — quiet hours do not hold it. All
three follow from `classes.CLASS_FOR_TRIGGER`, which is where that cell lives;
this module reads it rather than carrying its own `if trigger is USER_REMINDER`,
so the three behaviours cannot drift apart from each other.

The consequence worth stating plainly: a day can contain three user reminders
AND a festival greeting. That is not a cap breach, because the reminders are
Class T and §23.1 exempts Class T from the cap. §23.9 makes a cap breach
release-blocking, so the distinction is checked rather than assumed —
`test_a_reminder_does_not_spend_the_slot` and `test_five_sends_land_three`
are the two halves.

── Ties ────────────────────────────────────────────────────────────────────

"highest wins, tie-broken by user's engagement history". Priority is a TOTAL
order over the six, so two candidates can only tie by being the same trigger —
two festivals tomorrow, two open concerns from last night. Engagement is
recorded per trigger, so it cannot separate those either. Rather than pretend
otherwise, `select` sorts by (priority, -engagement, candidate id) and the id
is the honest last key: when the spec's two rules have both been applied and
still do not decide, the answer is at least the SAME every time, instead of
whichever order the caller happened to build its list in.

── Auto-pause ──────────────────────────────────────────────────────────────

"any trigger with open-rate <15% trailing 14 days is auto-paused and flagged."

`auto_paused` computes it from observations rather than reading a stored flag —
the discipline `release_gates` uses on the capability matrices, and for the
same reason: a stored pause flag stays set after the copy is fixed.

A trigger with NO sends in the window has no open rate — undefined, not zero —
and is not paused. That is derived from §23.2 rather than chosen: a rate is a
ratio and there is no ratio without a denominator. It also makes the pause
self-healing, which matters because §23.2 pairs the pause with "and flagged": a
paused trigger sends nothing, so fourteen days later its window is empty, its
rate is undefined and it resumes — the pause buys time for the human who was
flagged, and does not quietly become permanent.

**Known and deliberately not patched:** §23.2 states no minimum sample, so a
trigger that sent once and was not opened reads as 0% and pauses. Choosing a
minimum here would be inventing a number in the file whose whole subject is a
number the spec DID state (`notifications.trigger_sample_floor`, and the release
gate names it).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from zoneinfo import ZoneInfo

from sitara_schemas.notifications import (
    CONTEXTUAL_DAILY_CAP,
    CONTEXTUAL_TRIGGER_PRIORITY,
    MUHURAT_REMINDER_LEAD_HOURS,
    REENGAGEMENT_MAX_PER_WEEK,
    REENGAGEMENT_QUIET_DAYS,
    TRIGGER_AUTOPAUSE_OPEN_RATE,
    TRIGGER_AUTOPAUSE_WINDOW_DAYS,
    ContextualTrigger,
    MessageClass,
    NotificationCategory,
)

from sitara_api.notifications.classes import CLASS_FOR_TRIGGER


class TtlRule(StrEnum):
    """How a trigger's `expires_at` is computed (§23.4's "trigger-specific TTLs").

    Two rules, and only one of them is stated in the spec. §23.4 gives the
    muhurat case by name — "muhurat reminder expires when the window opens" —
    because a reminder that arrives after the window has opened is worse than
    no reminder: it tells someone they have missed something.

    `END_OF_LOCAL_DAY` is the default for the other four and is a reading of
    §23.4's principle rather than a sentence from it. Each of those four is a
    statement about TODAY — a festival today, an open concern to revisit today,
    a transit flagged today — so it stops being true at midnight local. Stated
    here rather than left implicit so that a trigger which needs something else
    has to say so.
    """

    UNTIL_WINDOW_OPENS = "until_window_opens"
    END_OF_LOCAL_DAY = "end_of_local_day"


@dataclass(frozen=True)
class TriggerSpec:
    """One row of §23.2's catalogue."""

    trigger: ContextualTrigger
    #: §23.2's own numbering, 1 highest. Read from the schema's priority tuple.
    priority: int
    message_class: MessageClass
    #: Whether awarding this trigger spends the day's one Class-C slot.
    consumes_slot: bool
    #: Which §23.5 toggle switches it off.
    category: NotificationCategory
    ttl_rule: TtlRule
    spec_ref: str


def _spec_for(trigger: ContextualTrigger, priority: int) -> TriggerSpec:
    message_class = CLASS_FOR_TRIGGER[trigger]
    return TriggerSpec(
        trigger=trigger,
        priority=priority,
        message_class=message_class,
        # DERIVED, never listed. §23.2 gives one reason for trigger 1's
        # exemption — "it is Class T, user-initiated" — so the exemption is a
        # consequence of the class rather than a second fact beside it. A
        # hand-written `consumes_slot=False` here would be a place for the two
        # to disagree, and the disagreement would look like a cap breach.
        consumes_slot=message_class is MessageClass.CONTEXTUAL,
        category=(
            NotificationCategory.FESTIVAL
            if trigger is ContextualTrigger.FESTIVAL_OR_FAMILY
            else NotificationCategory.CONTEXTUAL
        ),
        ttl_rule=(
            TtlRule.UNTIL_WINDOW_OPENS
            if trigger is ContextualTrigger.MUHURAT_WINDOW
            else TtlRule.END_OF_LOCAL_DAY
        ),
        spec_ref=f"§23.2({priority})",
    )


#: The catalogue, in §23.2's priority order.
CATALOGUE: Mapping[ContextualTrigger, TriggerSpec] = {
    trigger: _spec_for(trigger, priority)
    for priority, trigger in enumerate(CONTEXTUAL_TRIGGER_PRIORITY, start=1)
}


@dataclass(frozen=True)
class Candidate:
    """Something that has become eligible to be said today.

    `id` is the candidate's own stable identity — the muhurat's id, the
    festival's slug, the reminder's row id. It is what makes a re-run of the
    selector deterministic and what the notification's `message_id` is derived
    from, so two ticks that see the same candidate do not send twice (§23.4).
    """

    trigger: ContextualTrigger
    id: str
    #: §23.2(5) only: "relevance score above threshold". Left at 0.0 by every
    #: other trigger, and never used for ordering — §23.2 orders by TRIGGER,
    #: and a relevance that could out-rank a higher trigger would quietly
    #: replace the catalogue's priority with the ranking engine's.
    relevance: float = 0.0
    #: §23.2(2) only: when the muhurat window opens. Drives the TTL.
    window_opens_at: dt.datetime | None = None


class DeclineReason(StrEnum):
    """Why a candidate did not get the slot. Recorded, not discarded — §23.8
    reports the trigger mix, and a mix that only counts winners cannot show
    that one trigger has been crowding out five others all month."""

    SLOT_TAKEN = "slot_taken"
    TRIGGER_PAUSED = "trigger_paused"
    CATEGORY_OFF = "category_off"


@dataclass(frozen=True)
class Selection:
    """What §23.2 admits from one day's candidates."""

    admitted: tuple[Candidate, ...]
    declined: tuple[tuple[Candidate, DeclineReason], ...]

    @property
    def slot_spent(self) -> bool:
        return any(CATALOGUE[c.trigger].consumes_slot for c in self.admitted)


def select(
    candidates: Iterable[Candidate],
    *,
    engagement: Mapping[ContextualTrigger, float] | None = None,
    paused: frozenset[ContextualTrigger] = frozenset(),
    categories_off: frozenset[NotificationCategory] = frozenset(),
    slot_already_spent: bool = False,
) -> Selection:
    """§23.2's award: every Class-T reminder, plus at most one Class-C message.

    `slot_already_spent` is what makes this safe to call more than once in a
    day — the §7.1 wave and an on-open path both reach it — without the second
    call handing out a second contextual message.
    """
    engagement = engagement or {}
    ordered = sorted(
        candidates,
        key=lambda c: (
            CATALOGUE[c.trigger].priority,
            -engagement.get(c.trigger, 0.0),
            c.id,
        ),
    )

    admitted: list[Candidate] = []
    declined: list[tuple[Candidate, DeclineReason]] = []
    slots_left = 0 if slot_already_spent else CONTEXTUAL_DAILY_CAP

    for candidate in ordered:
        spec = CATALOGUE[candidate.trigger]
        if spec.category in categories_off:
            declined.append((candidate, DeclineReason.CATEGORY_OFF))
            continue
        if candidate.trigger in paused:
            declined.append((candidate, DeclineReason.TRIGGER_PAUSED))
            continue
        if not spec.consumes_slot:
            # §23.2(1). Not counted, not capped, not ordered against the rest —
            # it was already ahead of them, and it would still be admitted if
            # it were not.
            admitted.append(candidate)
            continue
        if slots_left <= 0:
            declined.append((candidate, DeclineReason.SLOT_TAKEN))
            continue
        admitted.append(candidate)
        slots_left -= 1

    return Selection(admitted=tuple(admitted), declined=tuple(declined))


def expires_at(
    candidate: Candidate,
    *,
    local_date: str,
    timezone: str,
) -> dt.datetime:
    """§23.4's trigger-specific TTL, in UTC.

    The muhurat rule is the one §23.4 names. It falls back to end-of-day when a
    candidate arrives without a window instant — which is a caller bug rather
    than a state, and failing toward the SHORTER-lived of the two available
    answers is what keeps a bug from turning into a reminder that outlives the
    thing it is about.
    """
    zone = ZoneInfo(timezone)
    spec = CATALOGUE[candidate.trigger]
    if spec.ttl_rule is TtlRule.UNTIL_WINDOW_OPENS and candidate.window_opens_at:
        return candidate.window_opens_at.astimezone(dt.UTC)
    date = dt.date.fromisoformat(local_date)
    midnight = dt.datetime(
        date.year, date.month, date.day, tzinfo=zone
    ) + dt.timedelta(days=1)
    return midnight.astimezone(dt.UTC)


def muhurat_is_near(window_opens_at: dt.datetime, now: dt.datetime) -> bool:
    """§23.2(2): "a muhurat window the user asked about is approaching (≤2h)".

    Both ends matter. A window more than two hours out is not yet eligible, and
    one that has already opened is not eligible at all — a reminder that lands
    after the window opens is a message telling somebody they missed something.
    """
    lead = window_opens_at - now
    return dt.timedelta(0) < lead <= dt.timedelta(hours=MUHURAT_REMINDER_LEAD_HOURS)


def reengagement_is_due(
    *, quiet_days: int, sent_in_last_week: int
) -> bool:
    """§23.2(6): "3+ quiet days → ONE gentle check-in per week maximum".

    Two conditions and they are not the same one. The quiet-day count is what
    makes her eligible; the weekly count is what stops the eligibility from
    firing every day she stays quiet — which is precisely the drumbeat §29.2
    forbids, and which a naive reading of "3+ quiet days" produces on day four,
    day five and day six.
    """
    return quiet_days >= REENGAGEMENT_QUIET_DAYS and (
        sent_in_last_week < REENGAGEMENT_MAX_PER_WEEK
    )


@dataclass(frozen=True)
class TriggerObservation:
    """§23.8's per-trigger counters over §23.2's trailing window."""

    trigger: ContextualTrigger
    sent: int
    opened: int

    @property
    def open_rate(self) -> float | None:
        """None when nothing was sent — undefined, not zero. See the header."""
        return None if self.sent == 0 else self.opened / self.sent


def auto_paused(
    observations: Sequence[TriggerObservation],
) -> frozenset[ContextualTrigger]:
    """§23.2's "<15% trailing 14 days is auto-paused and flagged".

    Strictly below: a trigger sitting exactly at the threshold is not paused,
    which is what "<15%" says and what a `<=` would quietly change.
    """
    return frozenset(
        o.trigger
        for o in observations
        if o.open_rate is not None and o.open_rate < TRIGGER_AUTOPAUSE_OPEN_RATE
    )


def autopause_window(now: dt.datetime) -> dt.datetime:
    """The start of §23.2's trailing window."""
    return now - dt.timedelta(days=TRIGGER_AUTOPAUSE_WINDOW_DAYS)


assert set(CATALOGUE) == set(ContextualTrigger), (
    "SPEC §23.2: the catalogue is closed — every trigger has a row and no row "
    "names a trigger the schema does not"
)
assert sum(1 for s in CATALOGUE.values() if not s.consumes_slot) == 1, (
    "SPEC §23.2: exactly one trigger is exempt from the contextual slot, and "
    "it is the user-requested reminder. A second exemption would make the "
    "1/day cap a suggestion."
)
