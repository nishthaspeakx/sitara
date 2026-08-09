"""§7.1's priority queues: "paying users > trial > dormant".

Three queues and an ordering, and the ordering is what defines membership: a
user is PAYING if they pay, else TRIAL if they are inside a trial, else
DORMANT. Dormancy is therefore the residual — post-trial free and lapsed
accounts — not a fourth dimension crossed with the other two.

That reading matters because the alternative is worse in a way that shows up
in production rather than in review. If dormancy were orthogonal ("has not
opened the app lately"), a paying subscriber who took a fortnight's holiday
would come home to no brief, having paid for one every day of it. §7.1's
justification for skipping dormant users is "no waste", and there is no waste
to save on a user who is paying: §28.2's Free variant already tells us the
residual tier sees generic panchang and locked personal cards, so there is no
personalised brief to pre-generate for them in the first place.

The engagement signal still earns its keep — it decides whether a residual user
is worth an on-open generation path at all, and it feeds §23.2's re-engagement
trigger — but it never demotes someone who is paying.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sitara_api.daily_guidance.types import Tier

#: Subscription statuses that mean "this account is currently entitled".
#: `past_due` is deliberately included: §22.13's dunning window keeps "full
#: features intact during grace" (§28.2's payment-grace variant), and cutting
#: the morning brief off at the first failed mandate debit would be exactly the
#: punitive pattern §29.2 forbids.
ENTITLED_STATUSES: frozenset[str] = frozenset({"active", "past_due", "in_grace"})

#: Plans that are a trial rather than a payment.
TRIAL_PLANS: frozenset[str] = frozenset({"trial"})


@dataclass(frozen=True)
class Entitlement:
    """What the subscription layer knows, reduced to what §7.1 needs.

    Assembled by the repository from `subscriptions`; kept as its own shape so
    the tiering rule below is pure and can be tested without a database.
    """

    plan: str | None = None
    status: str | None = None
    trial_ends_at: dt.datetime | None = None

    @property
    def entitled(self) -> bool:
        return bool(self.status and self.status in ENTITLED_STATUSES)


def tier_for(entitlement: Entitlement, *, now: dt.datetime) -> Tier:
    """§7.1's queue for this account. Total: every account gets exactly one."""
    if not entitlement.entitled:
        return Tier.DORMANT
    if entitlement.plan in TRIAL_PLANS:
        # A trial whose end has passed without conversion is not a trial any
        # more, whatever the subscription row still says — the nightly
        # reconciliation may not have run yet, and the wave should not spend a
        # Claude call on the strength of a stale status.
        if entitlement.trial_ends_at is not None and entitlement.trial_ends_at <= now:
            return Tier.DORMANT
        return Tier.TRIAL
    return Tier.PAYING


def generates_ahead(tier: Tier) -> bool:
    """§7.1: dormant users "get on-open generation only — no waste"."""
    return tier is not Tier.DORMANT
