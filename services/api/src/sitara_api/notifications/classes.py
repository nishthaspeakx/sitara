"""§23.1's four classes and what each one is ALLOWED to do.

§23.1 opens with the constraint that shapes this whole module:

    "behaviour differs by class — hard-coded, not configurable per template"

So this is a table in code, not a collection of template flags, and it is the
one place any of these questions is answered. A template that could set
`bypass_quiet_hours` would be a template that could wake somebody at 3am to
sell them an annual plan; the reason §23.1 hard-codes it is that the pressure
to make an exception is real and always arrives one template at a time.

── What the table encodes, and why each cell is where it is ────────────────

**Only Class T bypasses quiet hours and the 3/day cap.** §23.1 gives it both,
and it gives them to nothing else. The membership is what keeps that safe:
OTP, payment receipts and failures, mandate pre-debit notices, security alerts,
data-export ready, and §9's L4 safety resources. Every one of them is either a
thing the user just did or a thing that will cost them money or safety if it
waits until morning.

**`may_carry_marketing` is False for T, and it is a separate cell from
`requires_separate_consent`.** §23.1's clause is "no marketing content ever",
and the reason it needs its own cell rather than falling out of the consent
cell is §22.13: dunning nudges are Class T (utility, about an existing mandate)
and are therefore exempt from quiet hours and the cap — which makes Class T
exactly the class somebody would reach for to get a win-back past a cap.

**The unsubscribe header is on M and NOT on T.** §23.3: "one-click unsubscribe
headers (List-Unsubscribe) on Class M, never on Class T." Putting one on an OTP
mail invites a user to unsubscribe from the thing that lets them sign in, and
some clients act on the header without asking.

**Priority is T > D > C > M** (§23.7), expressed as a number where LOWER wins,
because that is what a queue ordering means and a boolean pair would not
survive a fifth class the way §23.1 says there will never be one.

Two import-time asserts keep the table honest — the same device
`daily_guidance/ranking.py` uses on the seventeen modules. They are asserts and
not tests because a table this small is read by every send, and a wrong cell
here is not a failing screen, it is a message that went out.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from sitara_schemas.notifications import (
    MARKETING_WEEKLY_CAP,
    ContextualTrigger,
    MessageClass,
    NotificationCategory,
)


@dataclass(frozen=True)
class ClassPolicy:
    """What §23.1 permits this class. Every field is a sentence from §23.1."""

    message_class: MessageClass

    #: §23.1 — T "bypasses quiet hours". Nothing else does, and §32.6's morning
    #: exception is NOT this cell: it belongs to one appointment rather than to
    #: a class, and lives in `quiet_hours.py` where that distinction is made.
    bypasses_quiet_hours: bool

    #: §23.1 — T "bypasses the 3/day cap".
    bypasses_daily_cap: bool

    #: §23.1 — T is "never suppressed". §23.5's "pause everything for a week"
    #: states its own exemption in the same words, which is why the preference
    #: centre reads this cell rather than carrying a second list.
    suppressible: bool

    #: §23.7 — "Dedicated Celery queues per class (T > D > C > M priority)".
    #: Lower is higher priority.
    queue_priority: int

    #: §23.1 — M has "separate legal consent (default OFF)".
    requires_separate_consent: bool

    #: §23.1 — M is "hard-capped 2/week". None means no per-class weekly cap;
    #: the 3/day cap is a separate cell because it applies across classes.
    weekly_cap: int | None

    #: §23.3 — "one-click unsubscribe headers (List-Unsubscribe) on Class M,
    #: never on Class T".
    unsubscribe_header: bool

    #: §23.1 — "no marketing content ever" on T. Its own cell rather than the
    #: inverse of the consent cell; see the module header.
    may_carry_marketing: bool


#: §23.1's table. The only declaration of any of it.
POLICIES: Mapping[MessageClass, ClassPolicy] = {
    MessageClass.TRANSACTIONAL: ClassPolicy(
        message_class=MessageClass.TRANSACTIONAL,
        bypasses_quiet_hours=True,
        bypasses_daily_cap=True,
        suppressible=False,
        queue_priority=0,
        requires_separate_consent=False,
        weekly_cap=None,
        unsubscribe_header=False,
        may_carry_marketing=False,
    ),
    MessageClass.DAILY_LOOP: ClassPolicy(
        message_class=MessageClass.DAILY_LOOP,
        bypasses_quiet_hours=False,
        bypasses_daily_cap=False,
        suppressible=True,
        queue_priority=1,
        requires_separate_consent=False,
        weekly_cap=None,
        unsubscribe_header=False,
        may_carry_marketing=False,
    ),
    MessageClass.CONTEXTUAL: ClassPolicy(
        message_class=MessageClass.CONTEXTUAL,
        bypasses_quiet_hours=False,
        bypasses_daily_cap=False,
        suppressible=True,
        queue_priority=2,
        requires_separate_consent=False,
        weekly_cap=None,
        unsubscribe_header=False,
        may_carry_marketing=False,
    ),
    MessageClass.MARKETING: ClassPolicy(
        message_class=MessageClass.MARKETING,
        bypasses_quiet_hours=False,
        bypasses_daily_cap=False,
        suppressible=True,
        queue_priority=3,
        requires_separate_consent=True,
        weekly_cap=MARKETING_WEEKLY_CAP,
        unsubscribe_header=True,
        may_carry_marketing=True,
    ),
}


#: §23.5's five toggles → the §23.1 class each one is delivered under.
#:
#: The two sets are deliberately different sizes and this map is the whole
#: reason: a CLASS is behaviour the code hard-codes and a CATEGORY is a choice
#: the user makes. Class T appears nowhere here, which is §23.5 saying an OTP
#: is not something to offer a toggle for; and Class C appears twice, because
#: someone who wants festival greetings and no transit nudges is an ordinary
#: person rather than an edge case.
CLASS_FOR_CATEGORY: Mapping[NotificationCategory, MessageClass] = {
    NotificationCategory.MORNING: MessageClass.DAILY_LOOP,
    NotificationCategory.NIGHT: MessageClass.DAILY_LOOP,
    NotificationCategory.CONTEXTUAL: MessageClass.CONTEXTUAL,
    NotificationCategory.FESTIVAL: MessageClass.CONTEXTUAL,
    NotificationCategory.MARKETING: MessageClass.MARKETING,
}


#: §23.2's catalogue → the class each trigger is delivered under.
#:
#: Five of the six are Class C. Trigger 1 is Class T, and that single cell is
#: what makes §23.2's "always wins, and does NOT consume the contextual slot
#: (it is Class T, user-initiated)" a fact about the code rather than a
#: sentence in a comment: a reminder the user asked for is not a message we
#: decided to send, so it is not competing for the slot and it is not held by
#: quiet hours. `catalogue.py` derives both behaviours from here rather than
#: carrying its own `if trigger is USER_REMINDER`.
CLASS_FOR_TRIGGER: Mapping[ContextualTrigger, MessageClass] = {
    ContextualTrigger.USER_REMINDER: MessageClass.TRANSACTIONAL,
    ContextualTrigger.MUHURAT_WINDOW: MessageClass.CONTEXTUAL,
    ContextualTrigger.FESTIVAL_OR_FAMILY: MessageClass.CONTEXTUAL,
    ContextualTrigger.REFLECTION_FOLLOWUP: MessageClass.CONTEXTUAL,
    ContextualTrigger.TRANSIT_CHANGE: MessageClass.CONTEXTUAL,
    ContextualTrigger.QUIET_REENGAGEMENT: MessageClass.CONTEXTUAL,
}


def policy(message_class: MessageClass) -> ClassPolicy:
    """§23.1's row for this class. Total over the enum, so no default."""
    return POLICIES[message_class]


def queue_order() -> tuple[MessageClass, ...]:
    """§23.7's T > D > C > M, read from the table rather than re-listed.

    `scheduling.celery_app` builds one queue per class from this, so the
    worker's `-Q` list and the priority the table declares cannot disagree.
    """
    return tuple(sorted(POLICIES, key=lambda c: POLICIES[c].queue_priority))


# ---------------------------------------------------------------------------
# Import-time asserts. §23.1's exemptions are the cells a future edit would
# most plausibly widen, one template at a time, each time for a good reason.
# ---------------------------------------------------------------------------

_EXEMPT = tuple(
    c
    for c, p in POLICIES.items()
    if p.bypasses_quiet_hours or p.bypasses_daily_cap or not p.suppressible
)
assert _EXEMPT == (MessageClass.TRANSACTIONAL,), (
    "SPEC §23.1: exactly ONE class bypasses quiet hours, bypasses the 3/day cap "
    f"and is never suppressed — Class T. Found: {_EXEMPT}"
)

assert not POLICIES[MessageClass.TRANSACTIONAL].may_carry_marketing, (
    "SPEC §23.1: Class T carries 'no marketing content ever'. It is the class "
    "that bypasses quiet hours and the cap, so this is the cell a win-back "
    "would be routed through if it were ever True — and §22.13's dunning being "
    "legitimately Class T is what makes that a live temptation rather than a "
    "hypothetical one."
)

assert [POLICIES[c].queue_priority for c in queue_order()] == [0, 1, 2, 3], (
    "SPEC §23.7: queue priority is T > D > C > M with no ties — a tie would "
    "make the worker's ordering depend on dict iteration order"
)

assert set(CLASS_FOR_CATEGORY) == set(NotificationCategory), (
    "every §23.5 toggle must name the class it is delivered under, or a "
    "category exists that no queue would carry"
)
assert set(CLASS_FOR_TRIGGER) == set(ContextualTrigger), (
    "every §23.2 trigger must name its class, or a trigger exists whose "
    "quiet-hours and cap behaviour is undefined"
)
