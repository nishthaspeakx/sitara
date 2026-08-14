"""The voice-minute pool, and the meter that spends it (§7.3, §29, §32.9).

Pure and clock-injected on purpose. Everything here is arithmetic over a
monotonic clock and a quota, and the two failures it exists to prevent — a user
charged for minutes they did not speak, and a call cut without the warnings
§32.9 promises — are both reproducible in milliseconds with no socket, no
vendor and no database. The Mongo half is `MinuteLedger` at the bottom, which
is a read and a write and nothing else.

Where the numbers come from, and where the spec disagrees with itself
---------------------------------------------------------------------

§29's channel table is the specific statement and this file follows it:

    voice-minute pool (§7.3): trial 60 · monthly 300 · annual/premium
    900/unlimited-fair-use

§7.3's own sentence says "fair-use: 300 min/mo Basic, 900 Premium", which uses
"Premium" for the 900 that §29 gives to *annual*. The two agree on every number
and disagree on one label. Recorded here rather than silently resolved, because
a reader who checks this file against §7.3 will find the mismatch and should
find it already known.

**The unlimited tier has no invented ceiling.** §7.3 says a soft limit ends in
"a gentle in-locale notice + text-mode" and names no number for it. So
`quota_minutes` is None, no warning ever fires, and no call is ever cut on it.
Picking a plausible ceiling here would be inventing the one number a user would
eventually be told they had exceeded.

Why the trial pool is not monthly
---------------------------------

§10-20 makes the trial seven days. Sixty minutes over a seven-day trial is a
trial-total, and a "monthly" reading of it would silently double the pool for
anyone whose trial straddled a month boundary. `period_start_for` makes that a
declared difference rather than an accident of arithmetic.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field
from enum import StrEnum

from sitara_schemas import ENTITLEMENT_WARNING_MINUTES

logger = logging.getLogger(__name__)


class CallPlan(StrEnum):
    """What a `subscriptions.plan` means for §25.3's minutes.

    `NONE` is a real member, not a null: an account with no active subscription
    and no live trial has a pool of zero, and zero is a designed state that the
    call affordance reads. Modelling it as an absence would have made "no plan"
    and "plan unreadable" the same value, and those must degrade differently.
    """

    TRIAL = "trial"
    MONTHLY = "monthly"
    ANNUAL = "annual"
    PREMIUM = "premium"
    NONE = "none"


#: §29's row. None = §7.3's unlimited fair-use tier — see the module docstring
#: for why it carries no invented ceiling.
MINUTE_POOL: dict[CallPlan, int | None] = {
    CallPlan.TRIAL: 60,
    CallPlan.MONTHLY: 300,
    CallPlan.ANNUAL: 900,
    CallPlan.PREMIUM: None,
    CallPlan.NONE: 0,
}


@dataclass(frozen=True)
class Entitlement:
    """What the §25.3 plan chip renders, and what the meter spends.

    `used_minutes` is a float because seconds are what actually accrue; the
    chip rounds and the meter does not. Rounding at the point of accrual is how
    a hundred short calls cost nothing.
    """

    plan: CallPlan
    quota_minutes: int | None
    used_minutes: float
    period_start: dt.datetime | None = None

    @property
    def unlimited(self) -> bool:
        return self.quota_minutes is None

    @property
    def remaining_minutes(self) -> float | None:
        """None when unlimited. Never negative: a pool that has been overrun
        reads as empty, because "−3 minutes left" is not a thing to render and
        a negative would sort below zero in every comparison downstream."""
        if self.quota_minutes is None:
            return None
        return max(0.0, self.quota_minutes - self.used_minutes)

    @property
    def exhausted(self) -> bool:
        remaining = self.remaining_minutes
        return remaining is not None and remaining <= 0

    def as_chip(self) -> dict[str, object]:
        """§25.3's plan chip, as data.

        The chip's SENTENCE is a catalog key on the client (§2.4); this is the
        three values it needs to choose between "⏳ unlimited" and "⏳ N min
        left". `minutes_left` is floored, not rounded: telling someone they have
        4 minutes when they have 3.6 is a promise the meter will break.
        """
        remaining = self.remaining_minutes
        return {
            "plan": self.plan.value,
            "unlimited": self.unlimited,
            "minutes_left": None if remaining is None else int(remaining),
            "minutes_quota": self.quota_minutes,
        }


def period_start_for(
    plan: CallPlan, *, subscribed_at: dt.datetime | None, now: dt.datetime
) -> dt.datetime | None:
    """When the current pool began filling.

    Monthly and annual plans meter per calendar month **anchored on the
    subscription's own day**, not on the 1st: a subscription taken on the 20th
    that reset on the 1st would hand its first month eleven days of free
    minutes, and every month after that would end on a different day from the
    one the user is billed on.

    A trial has ONE period — the whole trial (§10-20: seven days) — so this
    returns the trial's start and never rolls it forward.

    Returns None for the unlimited and no-plan cases, where there is nothing to
    reset. **This is the seam the billing module replaces.** When §30.3's
    lifecycle lands it owns the period boundary and this becomes one call into
    it; until then the anniversary rule is stated rather than assumed.
    """
    if plan in (CallPlan.PREMIUM, CallPlan.NONE) or subscribed_at is None:
        return None
    if plan is CallPlan.TRIAL:
        return subscribed_at

    anchor_day = subscribed_at.day
    # Walk back to this month's anniversary; if it has not happened yet this
    # month, the period began last month. `min(day, 28)` keeps a 31st-of-the-
    # month subscription from skipping February entirely — the boundary moves,
    # the pool never vanishes.
    day = min(anchor_day, 28)
    candidate = now.replace(
        day=day, hour=subscribed_at.hour, minute=subscribed_at.minute,
        second=0, microsecond=0,
    )
    if candidate > now:
        month = candidate.month - 1 or 12
        year = candidate.year - (1 if candidate.month == 1 else 0)
        candidate = candidate.replace(year=year, month=month)
    return max(candidate, subscribed_at)


@dataclass
class MinuteMeter:
    """One call's spend against one pool (§7.3, §32.9, §32.11).

    Three rules, and each is a sentence of the spec rather than a design choice:

    - **It is started and stopped explicitly.** §32.9: "metering stops the
      moment the session is text-mode". §32.11: "metering resumed only on
      resume". A meter that ran off wall-clock from `session.start` would
      charge a user for the four minutes they spent reading a handoff notice.
    - **Each warning fires once.** §32.9 says "once each", and the once-ness
      lives here rather than in a client that could be reloaded. `_fired` is
      what makes a reconnect inside the resume window not re-announce the
      five-minute warning the user already heard.
    - **It never fires a warning it has passed.** Crossing from 6.0 to 1.5
      minutes remaining in one tick — which a long synthesis does — must yield
      the 2-minute warning, not the 5-minute one and then silence. Both
      thresholds are checked against the new remaining value on every tick.
    """

    entitlement: Entitlement
    #: Seconds spent in THIS call. Kept separately from the pool's recorded
    #: history so a call can be metered before its row is written and the two
    #: never double-count.
    elapsed_seconds: float = 0.0
    _running_since: float | None = None
    _fired: set[int] = field(default_factory=set)

    def start(self, monotonic_now: float) -> None:
        if self._running_since is None:
            self._running_since = monotonic_now

    def stop(self, monotonic_now: float) -> None:
        """Idempotent. `session.end`, a handoff and a reap can all land on the
        same call, and a second stop that re-subtracted would refund minutes."""
        if self._running_since is None:
            return
        self.elapsed_seconds += max(0.0, monotonic_now - self._running_since)
        self._running_since = None

    @property
    def running(self) -> bool:
        return self._running_since is not None

    def spent_seconds(self, monotonic_now: float) -> float:
        if self._running_since is None:
            return self.elapsed_seconds
        return self.elapsed_seconds + max(0.0, monotonic_now - self._running_since)

    def remaining_minutes(self, monotonic_now: float) -> float | None:
        if self.entitlement.quota_minutes is None:
            return None
        pool_left = self.entitlement.remaining_minutes or 0.0
        return max(0.0, pool_left - self.spent_seconds(monotonic_now) / 60.0)

    def tick(self, monotonic_now: float) -> tuple[int, ...]:
        """Advance and report which of §32.9's thresholds were crossed now.

        Returns the thresholds in DESCENDING order, so a caller that crossed
        both in one tick announces "5" before "2" if it announces both — though
        it should announce only the last, which is why the value is a tuple the
        caller can take the tail of rather than a single number this function
        guesses at.
        """
        remaining = self.remaining_minutes(monotonic_now)
        if remaining is None:
            return ()
        crossed = [
            threshold
            for threshold in ENTITLEMENT_WARNING_MINUTES
            if remaining <= threshold and threshold not in self._fired
        ]
        self._fired.update(crossed)
        return tuple(crossed)

    def exhausted(self, monotonic_now: float) -> bool:
        remaining = self.remaining_minutes(monotonic_now)
        return remaining is not None and remaining <= 0.0


class MinuteLedger:
    """The Mongo half: read the plan, read the spend, write the session.

    §25.7 puts per-session metering in `voice_sessions`, and §6.4's validator on
    that collection structurally rejects any audio field — which is why the
    call's minutes go there and not into some new collection that would have to
    re-earn the same guarantee.
    """

    def __init__(self, db: object) -> None:
        self._db = db

    async def load(self, user_id: str, *, now: dt.datetime) -> Entitlement:
        """The user's pool as of `now`.

        **Fails toward the smallest pool, never toward the largest.** An
        unreadable subscription yields `CallPlan.NONE`, so the call affordance
        declines rather than granting nine hundred minutes to an account nobody
        could look up. The mirror image of §33.1's "fail closed toward privacy":
        when the evidence is missing, take the reading that cannot cost anyone
        anything they did not buy.
        """
        from sitara_api.chat_orchestration.store import to_object_id

        try:
            oid = to_object_id(user_id, field_name="user_id")
            subscription = await self._db.subscriptions.find_one(  # type: ignore[attr-defined]
                {"user_id": oid, "status": "active"}
            )
        except Exception:
            logger.warning("subscription unreadable; the call pool degrades to none (§7.3)")
            return Entitlement(plan=CallPlan.NONE, quota_minutes=0, used_minutes=0.0)

        plan = _plan_from(subscription)
        quota = MINUTE_POOL[plan]
        subscribed_at = (subscription or {}).get("created_at")
        period_start = period_start_for(plan, subscribed_at=subscribed_at, now=now)

        used = 0.0
        if quota is not None and quota > 0:
            used = await self._minutes_since(oid, period_start)
        return Entitlement(
            plan=plan,
            quota_minutes=quota,
            used_minutes=used,
            period_start=period_start,
        )

    async def _minutes_since(self, oid: object, since: dt.datetime | None) -> float:
        match: dict[str, object] = {"user_id": oid}
        if since is not None:
            match["created_at"] = {"$gte": since}
        try:
            cursor = self._db.voice_sessions.aggregate(  # type: ignore[attr-defined]
                [{"$match": match}, {"$group": {"_id": None, "minutes": {"$sum": "$minutes"}}}]
            )
            async for row in cursor:
                return float(row.get("minutes") or 0.0)
        except Exception:
            # Same direction as `load`: an unreadable spend reads as a FULL
            # pool spent, not an empty one. The user is not cut off — the caller
            # still gets a quota — but nothing here can silently grant minutes.
            logger.warning("voice-minute spend unreadable; treating the pool as spent")
            return float("inf")
        return 0.0

    async def record(
        self,
        *,
        user_id: str,
        conversation_id: str | None,
        seconds: float,
        provider_mix: dict[str, object],
        latency_stats: dict[str, object],
        now: dt.datetime,
    ) -> None:
        """One call's spend, at its end (§25.7).

        There is deliberately no audio field to pass. §6.4's validator on
        `voice_sessions` forbids one outright, so this signature could not grow
        one without the write failing — which is the shape §13/§33.1 asked for
        rather than a convention about what callers remember not to send.
        """
        from sitara_api.chat_orchestration.store import to_object_id
        from sitara_api.db.documents import stamp

        document = stamp(
            {
                "user_id": to_object_id(user_id, field_name="user_id"),
                "conversation_id": (
                    to_object_id(conversation_id, field_name="conversation_id")
                    if conversation_id
                    else None
                ),
                "minutes": round(seconds / 60.0, 4),
                "provider_mix": provider_mix,
                "latency_stats": latency_stats,
            },
            now=now,
        )
        await self._db.voice_sessions.insert_one(document)  # type: ignore[attr-defined]


def _plan_from(subscription: dict[str, object] | None) -> CallPlan:
    """A `subscriptions.plan` string → a pool.

    An UNRECOGNISED plan string is `NONE`, not a default of 300. §30.3 already
    contemplates plans this code has never seen — founding offers, gifts,
    store-billing wrappers — and the day one of them ships, the failure worth
    having is "calls are unavailable, please contact support" rather than a
    silent grant of somebody else's quota.
    """
    if not subscription:
        return CallPlan.NONE
    raw = str(subscription.get("plan") or "").strip().lower()
    try:
        return CallPlan(raw)
    except ValueError:
        logger.warning("unrecognised subscription plan; the call pool degrades to none")
        return CallPlan.NONE
