"""§22.13's ladder, as arithmetic (§30.3, §22.13, §28.2).

Pure and clock-injected, for the reason `voice/entitlements.py` gives about
minutes and this file inherits about days: everything §22.13 promises is a
comparison between two instants, and the failure it exists to prevent — access
withdrawn before the grace it was promised — is reproducible in microseconds
with no database, no rail and no clock of its own.

    active ──renewal fails──▶ grace ──7d──▶ read_only ──21d──▶ downgraded
       │                        │
       │                        └──paid──▶ active   (anchor preserved)
       │
       └──cancelled──▶ (access to period_end) ──▶ expired

── The one rule this module exists to make unbreakable ─────────────────────

**A failed renewal changes nothing about access for seven days.** Not "most
access", not "new guidance only" — nothing. §22.13 spends its whole paragraph
on this: the nudges are in-locale, the retry is one tap, and the state that
follows the grace is a read-only one whose own name is "your memories are
safe". The product's entire posture toward a customer whose bank said no is
that we do not punish her for it, and the failure mode is an off-by-one nobody
would notice in a demo.

So `access_at` takes the instant as an argument and computes, rather than
reading a status somebody remembered to update. A stored status can be stale —
the sweep may not have run, the process may have restarted — and a stale status
that says `downgraded` is a user locked out of something she is entitled to.
`project` is the same computation returning the status, and the store writes
what it returns rather than deciding for itself.

── Why `grace` and `read_only` are separate states ─────────────────────────

Because §22.13 gives them different promises, and a single "past due" flag with
a day counter beside it is a shape in which the two can be conflated by any
comparison that reads the flag and forgets the counter. Read the state; the
state carries the promise.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, replace
from enum import StrEnum

from sitara_schemas.payments import (
    GRACE_PERIOD_DAYS,
    READ_ONLY_PERIOD_DAYS,
    BillingRegion,
    PaymentFailureReason,
    PlanId,
    SubscriptionStatus,
)
from sitara_schemas.today import PlanState


class AccessLevel(StrEnum):
    """What a subscription entitles, right now.

    Deliberately NOT in `packages/schemas`. It is a RULE over the status rather
    than a value the wire carries, exactly as §32.1's Today `variant` is a rule
    over `TodayState` — and for the same reason: a client that received both
    the status and the access level could disagree with the server about their
    relationship, and the disagreement would be invisible until the one case
    they were computed differently for. The client receives the status; the
    server enforces the access.
    """

    #: Everything. §22.13's grace is here, and that is the whole section.
    FULL = "full"
    #: §22.13's 21 days: her own past is readable, new guidance is not
    #: generated. Nothing is deleted, and `retains_history` says so.
    READ_ONLY = "read_only"
    #: §28.2's free variant. Still not a deletion.
    NONE = "none"


#: Which statuses grant what. Declared as a table because the alternative is a
#: chain of `if`s in which `grace` eventually gets grouped with `read_only` by
#: someone who reads both as "not paying".
_ACCESS: dict[SubscriptionStatus, AccessLevel] = {
    # §30.3 — the UPI hold. Nothing has been collected, so nothing is granted.
    SubscriptionStatus.PENDING: AccessLevel.NONE,
    SubscriptionStatus.TRIALING: AccessLevel.FULL,
    SubscriptionStatus.ACTIVE: AccessLevel.FULL,
    # §22.13. The one line of this table that matters.
    SubscriptionStatus.GRACE: AccessLevel.FULL,
    SubscriptionStatus.READ_ONLY: AccessLevel.READ_ONLY,
    # §30.3 — "access till period end stated". She cancelled; she paid for now.
    SubscriptionStatus.CANCELLED: AccessLevel.FULL,
    SubscriptionStatus.DOWNGRADED: AccessLevel.NONE,
    SubscriptionStatus.EXPIRED: AccessLevel.NONE,
}

#: §28.2's four commercial variants, from the billing truth. The projection is
#: HERE and only here — `today`'s payload carries `PlanState` and S30 carries
#: `SubscriptionStatus`, and if each screen derived its own the two would
#: disagree about the same account on exactly the crowded morning §32.1 exists
#: for.
#:
#: `read_only` → `free` is the judgement worth stating: §28.2's free variant
#: "locks personal cards behind one calm CTA", which is precisely what a
#: read-only account should show — her past is there, new guidance is not.
#: Mapping it to `grace` would keep the amber banner showing full features she
#: no longer has.
_PLAN_STATE: dict[SubscriptionStatus, PlanState] = {
    SubscriptionStatus.PENDING: PlanState.FREE,
    SubscriptionStatus.TRIALING: PlanState.TRIAL,
    SubscriptionStatus.ACTIVE: PlanState.PREMIUM,
    SubscriptionStatus.GRACE: PlanState.GRACE,
    SubscriptionStatus.READ_ONLY: PlanState.FREE,
    # She paid for this period and §29.2 forbids selling to her during it.
    SubscriptionStatus.CANCELLED: PlanState.PREMIUM,
    SubscriptionStatus.DOWNGRADED: PlanState.FREE,
    SubscriptionStatus.EXPIRED: PlanState.FREE,
}

#: Terminal states. `project` never moves out of one, so a downgraded account
#: that is read a year later reads the same as one read the day it downgraded.
TERMINAL: frozenset[SubscriptionStatus] = frozenset(
    {SubscriptionStatus.DOWNGRADED, SubscriptionStatus.EXPIRED}
)


def is_live(status: SubscriptionStatus) -> bool:
    """Whether this row occupies the user's one subscription slot.

    A WIDER set than `active`, and that width is the point. §6.4's unique index
    is `user_id + status where status=active`, written when a subscription had
    two states; §22.13's ladder grants access under `trialing`, `grace`,
    `read_only` and `cancelled` as well, and every one of those is a row a
    second purchase could be made alongside — leaving two rows both granting
    access and a renewal job billing both of them.

    So `subscriptions.live` carries a second partial unique index, and this
    function is the ONLY derivation of it (applied in `store._document`). It is
    computed from the status rather than stored independently, because a
    derived field with two writers is a derived field that will eventually
    disagree with what it was derived from — and disagreeing here means either
    a double subscription or a user who cannot buy at all.

    `pending` is live: §30.3's UPI hold is a purchase in flight, and a second
    purchase started during those five minutes is precisely the double charge
    the hold screen exists to avoid. It grants no access (see `_ACCESS`), which
    is a different question.
    """
    return status not in TERMINAL


@dataclass(frozen=True)
class SubscriptionState:
    """One subscription, as the state machine sees it.

    Frozen: every transition returns a new value. A dunning ladder whose steps
    mutated the thing they were stepping would make "what did it look like
    before" unanswerable, and that question is most of an audit.
    """

    plan: PlanId
    region: BillingRegion
    status: SubscriptionStatus
    period_start: dt.datetime
    period_end: dt.datetime
    #: §22.13's clock starts here. None whenever the last renewal succeeded —
    #: and clearing it on recovery is what stops a stale grace banner.
    renewal_failed_at: dt.datetime | None = None
    failure_reason: PaymentFailureReason | None = None
    #: §30.3's post-purchase mandate rejection. NOT a status: the subscription
    #: is active on the paid period and this is a queued retry plus a screen.
    mandate_retry_required: bool = False
    #: §10-20's founding price, held on the row because §30.3 says it "does NOT
    #: transfer automatically across regions" — which is only checkable if we
    #: know she has one.
    founding: bool = False

    # -- computed ----------------------------------------------------------

    def project(self, now: dt.datetime) -> SubscriptionState:
        """The state as of `now`, advancing §22.13's clock.

        Idempotent and monotonic: projecting twice is projecting once, and no
        path here moves backwards. That is what lets the store write the result
        without a transaction — two workers projecting the same row concurrently
        compute the same answer.
        """
        if self.status in TERMINAL:
            return self

        if self.status is SubscriptionStatus.GRACE and self.renewal_failed_at is not None:
            if now >= self.read_only_at:  # type: ignore[operator]
                return replace(self, status=SubscriptionStatus.READ_ONLY).project(now)
            return self

        if self.status is SubscriptionStatus.READ_ONLY and self.renewal_failed_at is not None:
            if now >= self.downgrade_at:  # type: ignore[operator]
                return replace(self, status=SubscriptionStatus.DOWNGRADED)
            return self

        if self.status is SubscriptionStatus.CANCELLED and now >= self.period_end:
            return replace(self, status=SubscriptionStatus.EXPIRED)

        # A trial that ran out is not a lapse and gets no grace: §22.13's
        # dunning is about a renewal that failed, and nothing failed here —
        # nobody was ever charged. S31 is what follows (§28.2's free variant).
        if self.status is SubscriptionStatus.TRIALING and now >= self.period_end:
            return replace(self, status=SubscriptionStatus.DOWNGRADED)

        return self

    @property
    def read_only_at(self) -> dt.datetime | None:
        """When §22.13's 7-day grace ends. None when no renewal has failed."""
        if self.renewal_failed_at is None:
            return None
        return self.renewal_failed_at + dt.timedelta(days=GRACE_PERIOD_DAYS)

    @property
    def downgrade_at(self) -> dt.datetime | None:
        """When §22.13's 21 read-only days end. 28 days after the failure."""
        if self.renewal_failed_at is None:
            return None
        return self.renewal_failed_at + dt.timedelta(
            days=GRACE_PERIOD_DAYS + READ_ONLY_PERIOD_DAYS
        )

    def access_at(self, now: dt.datetime) -> AccessLevel:
        """What she may do, computed rather than read.

        Goes through `project` on purpose: a stored `grace` that the sweep has
        not advanced is a real state a real process will read, and answering
        from the stale value would grant full access weeks after a downgrade.
        The mirror of the rule that keeps this file honest in the other
        direction — nothing here may revoke early either.
        """
        return _ACCESS[self.project(now).status]

    def plan_state_at(self, now: dt.datetime) -> PlanState:
        """§28.2's commercial variant. One projection, one table."""
        return _PLAN_STATE[self.project(now).status]

    @property
    def retains_history(self) -> bool:
        """§22.13: "no hard deletion".

        A constant `True`, and it is a property rather than a comment because
        it is asserted from outside: `tests/payments` reads it on the
        downgraded state, so a future status that quietly meant "and delete
        her things" would have to change this line to ship, in front of a
        reviewer, rather than by omission.
        """
        return True


# ---------------------------------------------------------------------------
# Transitions. Each is one sentence of §30.3 or §22.13.
# ---------------------------------------------------------------------------


def start(
    *,
    plan: PlanId,
    region: BillingRegion,
    now: dt.datetime,
    term_days: int,
    founding: bool = False,
    pending: bool = False,
) -> SubscriptionState:
    """A purchase that the rail has accepted, or is holding (§30.3)."""
    return SubscriptionState(
        plan=plan,
        region=region,
        status=SubscriptionStatus.PENDING if pending else SubscriptionStatus.ACTIVE,
        period_start=now,
        period_end=now + dt.timedelta(days=term_days),
        founding=founding,
    )


def start_trial(*, region: BillingRegion, now: dt.datetime, term_days: int) -> SubscriptionState:
    """§10-20's seven days. Full-featured, and nothing was charged."""
    return SubscriptionState(
        plan=PlanId.TRIAL,
        region=region,
        status=SubscriptionStatus.TRIALING,
        period_start=now,
        period_end=now + dt.timedelta(days=term_days),
    )


def settle_pending(
    state: SubscriptionState, *, now: dt.datetime, term_days: int
) -> SubscriptionState:
    """§30.3's UPI hold resolving into a real grant.

    The term starts NOW rather than when the intent was opened: a user who took
    four minutes to approve in her UPI app has not spent four minutes of what
    she bought.
    """
    return replace(
        state,
        status=SubscriptionStatus.ACTIVE,
        period_start=now,
        period_end=now + dt.timedelta(days=term_days),
    )


def renew(state: SubscriptionState, *, term_days: int) -> SubscriptionState:
    """A collected renewal (§22.13).

    **The new period starts at the old `period_end`, never at `now`.** That is
    the billing anchor, and anchoring on the collection instant would walk
    every subscriber's renewal date forward by however long their bank took —
    permanently, and by more every cycle. It is also what makes a recovery
    inside the grace whole: she does not lose the days she spent in it.
    """
    return replace(
        state,
        status=SubscriptionStatus.ACTIVE,
        period_start=state.period_end,
        period_end=state.period_end + dt.timedelta(days=term_days),
        renewal_failed_at=None,
        failure_reason=None,
        mandate_retry_required=False,
    )


def fail_renewal(
    state: SubscriptionState, *, reason: PaymentFailureReason, now: dt.datetime
) -> SubscriptionState:
    """§22.13's grace begins.

    Look at what this does NOT touch: `plan`, `region`, `period_start`,
    `period_end`, `founding`. A failed renewal is a fact about the NEXT
    transaction, and the period she already paid for is a fact about a
    completed one. Rewriting `period_end` here — which is the tempting way to
    make the grace "end" — would destroy the record of what she bought.
    """
    if state.renewal_failed_at is not None:
        # Already in the ladder. A second failure must not restart the clock,
        # or a rail retrying daily would hold someone in grace forever — the
        # generous-looking version of never downgrading anyone, and equally a
        # bug, because §22.13's 28 days would never elapse.
        return state
    return replace(
        state,
        status=SubscriptionStatus.GRACE,
        renewal_failed_at=now,
        failure_reason=reason,
    )


def reject_mandate(state: SubscriptionState) -> SubscriptionState:
    """§30.3: "subscription active on paid period; mandate retry flow queued".

    One field. The status is untouched, which is the entire point.
    """
    return replace(state, mandate_retry_required=True)


def cancel(state: SubscriptionState) -> SubscriptionState:
    """§30.3's cancellation: immediate confirm, access till period end.

    No `now`, deliberately. Cancellation is not a scheduled thing that happens
    at a moment; it is a decision, and its effect on access is entirely carried
    by `period_end`, which `project` reads. A `now` parameter here would invite
    a future edit that ended access at it.
    """
    if state.status in TERMINAL:
        return state
    return replace(state, status=SubscriptionStatus.CANCELLED)


def extend(state: SubscriptionState, *, days: int) -> SubscriptionState:
    """Add a term. §30.3's gift credit conversion, and nothing else.

    It moves `period_end` and touches NOTHING else — not the plan, not the
    region, not the currency implied by the region. §30.3: "an active
    subscription always retains its original currency and rail until renewal —
    no mid-cycle conversion, ever". A gift bought in USD extends an INR
    subscription by adding TIME, which has no currency, and that is why this
    function takes days rather than money.

    A gift onto a lapsed subscription revives it, because the giver bought
    access and §22.13 deleted nothing.
    """
    revived = (
        SubscriptionStatus.ACTIVE
        if state.status in TERMINAL or state.status is SubscriptionStatus.READ_ONLY
        else state.status
    )
    base = max(state.period_end, state.period_start)
    return replace(
        state,
        status=revived,
        period_end=base + dt.timedelta(days=days),
        renewal_failed_at=None if revived is SubscriptionStatus.ACTIVE else state.renewal_failed_at,
        failure_reason=None if revived is SubscriptionStatus.ACTIVE else state.failure_reason,
    )


def migrate_region(
    state: SubscriptionState, *, region: BillingRegion, now: dt.datetime
) -> SubscriptionState:
    """§30.3's billing-region migration, and its one hard precondition.

    "An active subscription always retains its original currency and rail until
    renewal — no mid-cycle conversion, ever." So this REFUSES mid-cycle, rather
    than accepting and scheduling: a function that could be called at any time
    and quietly deferred is one whose callers stop knowing when it takes
    effect, and §30.3's rule is about the instant, not the intention.

    "Entitlements continue uninterrupted through migration" — so the period is
    untouched and only the region moves.

    "Promotional/founding pricing does NOT transfer automatically across
    regions (stated at switch)" — so `founding` is dropped, always. Carrying it
    would silently give a ₹2,999 founding subscriber a $79 renewal in a region
    whose founding offer they never took.
    """
    if now < state.period_end:
        raise MigrationRefused(
            "§30.3: an active subscription retains its original currency and rail "
            "UNTIL RENEWAL. This migration was requested mid-cycle, and there is no "
            "conversion available to perform one."
        )
    return replace(state, region=region, founding=False)


class MigrationRefused(ValueError):
    """A region change was asked for at a moment §30.3 forbids one."""
