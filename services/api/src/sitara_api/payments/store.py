"""The Mongo half of §30.3 — reads, writes, and the one uniqueness guarantee.

Deliberately thin. Every rule about WHAT a subscription may become is in
`lifecycle.py`, which is pure; this file knows how to turn one of those values
into a §6.4 document and back, and how to record a financial event exactly
once. Keeping the two apart is what let §22.13's ladder be tested at every day
boundary with no database at all.

── `live` is derived here and nowhere else ─────────────────────────────────

`subscriptions.live` carries the partial unique index that stops a user holding
two access-granting rows (see `db/registry.py`). It is computed from the status
by `lifecycle.is_live` at exactly one point — `_document` — because a derived
field written by more than one path is a derived field that will eventually
disagree with what it was derived from, and this one disagreeing means either a
double subscription or a user who cannot buy at all.

── Why the duplicate guard is the index and not the read ───────────────────

`record_event` inserts first and catches `DuplicateKeyError`, rather than
checking and then inserting. Between a check and an insert is precisely where
two webhook deliveries in two workers collide, and §30.3's promise has to hold
under concurrency or it is a promise about single-threaded test runs.
`tests/payments` forces that race with `_skip_precheck`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from sitara_schemas.payments import (
    BillingRegion,
    Currency,
    PaymentFailureReason,
    PlanId,
    SubscriptionStatus,
)

from sitara_api.chat_orchestration.store import to_object_id
from sitara_api.db.documents import stamp
from sitara_api.payments.gifting import Gift
from sitara_api.payments.lifecycle import SubscriptionState, is_live
from sitara_api.payments.money import Money
from sitara_api.payments.providers.base import PaymentProviderName, ProviderEvent

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StoredSubscription:
    """A row, plus the identity the row was found under.

    The `_id` travels with the state so a caller can assert the row was
    EXTENDED rather than replaced — which is the difference between §30.3's
    credit conversion and the version of it that destroys what the receiver
    already paid for. `tests/payments` reads it for exactly that.
    """

    id: ObjectId
    #: The owner. Carried on the value because `handle_event` resolves a
    #: subscription from a RAIL REFERENCE — a webhook names no user (§13 keeps
    #: our identifiers out of a vendor's system) — and every write that follows
    #: needs the owner it just found.
    user_id: str
    state: SubscriptionState
    provider: PaymentProviderName
    price: Money | None
    provider_sub_id: str | None


class PaymentStore:
    def __init__(self, db: Any) -> None:
        self._db = db

    # -- subscriptions -----------------------------------------------------

    async def find_live(self, user_id: str) -> StoredSubscription | None:
        """The user's one access-granting subscription, if she has one.

        Reads `live`, not `status`, so it finds her in grace and in read-only
        too. A lookup on `status: "active"` is how a lapsed subscriber's
        renewal retry ends up creating a second row beside the first.
        """
        row = await self._db.subscriptions.find_one(
            {"user_id": to_object_id(user_id, field_name="user_id"), "live": True}
        )
        return _hydrate(row) if row else None

    async def find_by_id(self, subscription_id: ObjectId) -> StoredSubscription | None:
        row = await self._db.subscriptions.find_one({"_id": subscription_id})
        return _hydrate(row) if row else None

    async def find_by_provider_ref(self, provider_ref: str) -> StoredSubscription | None:
        """The row a rail event belongs to.

        This is the JOIN between a webhook and an account, and it is the only
        one: `start_purchase` stores the rail's reference on the row, and the
        event carries it back. Nothing about the user travels to the rail.
        """
        row = await self._db.subscriptions.find_one({"provider_sub_id": provider_ref})
        return _hydrate(row) if row else None

    async def find_latest(self, user_id: str) -> StoredSubscription | None:
        """Her most recent subscription, live or not.

        S30 has to render a downgraded account — §22.13 ends in one and §28.2
        gives it a screen — and `find_live` correctly returns nothing for it.
        Two methods rather than a flag, because the callers want genuinely
        different things: the entitlement check wants live-or-nothing, and the
        screen wants the truth.
        """
        rows = self._db.subscriptions.find(
            {"user_id": to_object_id(user_id, field_name="user_id")}
        ).sort("created_at", -1).limit(1)
        async for row in rows:
            return _hydrate(row)
        return None

    async def upsert(
        self,
        *,
        user_id: str,
        state: SubscriptionState,
        provider: PaymentProviderName,
        price: Money | None,
        provider_sub_id: str | None,
        now: Any,
        subscription_id: ObjectId | None = None,
    ) -> StoredSubscription:
        """Write a state. Extends the existing row when there is one.

        `created_at` is preserved by `stamp`, which matters more here than
        anywhere else it applies: `voice/entitlements.period_start_for` reads
        `subscriptions.created_at` as the minute-pool anniversary, so a row
        rewritten with a fresh `created_at` would silently reset somebody's
        voice minutes to a different day of the month.
        """
        oid = to_object_id(user_id, field_name="user_id")
        target = subscription_id
        if target is None:
            existing = await self._db.subscriptions.find_one({"user_id": oid, "live": True})
            target = existing["_id"] if existing else ObjectId()

        document = stamp(
            {
                "_id": target,
                "user_id": oid,
                "provider": provider.value,
                "provider_sub_id": provider_sub_id,
                "gift_links": [],
                **self._state_fields(state),
                "price_minor": price.minor if price else None,
                "currency": price.currency.value if price else None,
            },
            now=now,
        )
        # `$setOnInsert` for `created_at` so an upsert onto an existing row
        # never rewrites it — see the docstring.
        created_at = document.pop("created_at")
        gift_links = document.pop("gift_links")
        await self._db.subscriptions.update_one(
            {"_id": target},
            {
                "$set": document,
                "$setOnInsert": {"created_at": created_at, "gift_links": gift_links},
            },
            upsert=True,
        )
        row = await self._db.subscriptions.find_one({"_id": target})
        return _hydrate(row)

    @staticmethod
    def _state_fields(state: SubscriptionState) -> dict[str, Any]:
        """A `SubscriptionState` as §6.4 columns.

        `live` is set HERE, from the status, and this is the only assignment to
        it in the codebase — see the module header.
        """
        return {
            "plan": state.plan.value,
            "region": state.region.value,
            "status": state.status.value,
            "period_start": state.period_start,
            "period_end": state.period_end,
            "renewal_failed_at": state.renewal_failed_at,
            "failure_reason": state.failure_reason.value if state.failure_reason else None,
            "mandate_retry_required": state.mandate_retry_required,
            "founding": state.founding,
            "live": is_live(state.status),
        }

    # -- payments ----------------------------------------------------------

    async def record_event(
        self,
        *,
        user_id: str,
        provider: PaymentProviderName,
        event: ProviderEvent,
        state: str,
        subscription_id: ObjectId | None,
        simulated: bool,
        now: Any,
    ) -> bool:
        """One financial row. Returns False when it was already recorded.

        Insert-then-catch, never check-then-insert — see the module header.
        §6.4's unique index on `provider_event_id` is the guard, so a race
        between two workers is resolved by MongoDB rather than by whichever
        read happened to run first.
        """
        document = stamp(
            {
                "user_id": to_object_id(user_id, field_name="user_id"),
                "provider": provider.value,
                "provider_event_id": event.provider_event_id,
                "idempotency_key": event.idempotency_key,
                "kind": event.kind.value,
                "state": state,
                "amount": event.amount.minor if event.amount else 0,
                "currency": event.amount.currency.value if event.amount else None,
                "failure_reason": (
                    event.failure_reason.value if event.failure_reason else None
                ),
                "invoice_ref": event.invoice_ref,
                # §6.4/§13 — a rail-side TOKEN, CSFLE-encrypted under the
                # `payment` key class. Never an instrument; the interface has
                # nowhere to put one.
                "instrument_ref": event.instrument_ref,
                "subscription_id": subscription_id,
                "simulated": simulated,
            },
            now=now,
        )
        try:
            await self._db.payments.insert_one(document)
        except DuplicateKeyError:
            logger.info(
                "duplicate provider event refused by the index (§30.3): %s",
                event.provider_event_id,
            )
            return False
        return True

    async def has_other_charge(
        self, *, idempotency_key: str, excluding_event_id: str
    ) -> bool:
        """Whether ANOTHER successful charge exists under this idempotency key.

        §30.3's second duplicate: two distinct event ids for one purchase. The
        unique index cannot catch it — the ids genuinely differ — so this read
        does, and the answer is a refund rather than a discard.

        **`excluding_event_id` is what makes it answerable at all.** The caller
        asks after recording the charge (see `service.handle_event` for why),
        so the row it is asking about is already in the collection; without the
        exclusion every first charge would find itself and refund itself.
        """
        return (
            await self._db.payments.count_documents(
                {
                    "idempotency_key": idempotency_key,
                    "kind": "payment.succeeded",
                    "state": "succeeded",
                    "provider_event_id": {"$ne": excluding_event_id},
                },
                limit=1,
            )
            > 0
        )

    async def receipts(self, *, user_id: str, limit: int = 24) -> list[dict[str, Any]]:
        """S30's receipt list, newest first."""
        cursor = (
            self._db.payments.find({"user_id": to_object_id(user_id, field_name="user_id")})
            .sort("created_at", -1)
            .limit(limit)
        )
        return [row async for row in cursor]

    # -- gifts -------------------------------------------------------------

    async def put_gift(self, gift: Gift, *, now: Any) -> None:
        await self._db.gifts.insert_one(
            stamp(
                {
                    "code": gift.code,
                    "buyer_user_id": to_object_id(gift.buyer_user_id, field_name="buyer_user_id"),
                    "plan": gift.plan.value,
                    "region": gift.region.value,
                    "value_minor": gift.value.minor,
                    "currency": gift.value.currency.value,
                    "term_days": gift.term_days,
                    "expires_at": gift.expires_at,
                    "redeemed_by_user_id": None,
                    "redeemed_at": None,
                    "redemption_outcome": None,
                },
                now=now,
            )
        )

    async def find_gift(self, code: str) -> Gift | None:
        row = await self._db.gifts.find_one({"code": code})
        return _hydrate_gift(row) if row else None

    async def claim_gift(
        self, *, code: str, user_id: str, outcome: str, now: Any
    ) -> bool:
        """Mark a gift redeemed, and refuse if someone got there first.

        The `redeemed_by_user_id: None` in the FILTER is the whole guard: it is
        a compare-and-swap, so two simultaneous redemptions of one code produce
        one winner and one `already_redeemed`. A read-then-write would produce
        two winners and two extensions from one purchase.
        """
        result = await self._db.gifts.update_one(
            {"code": code, "redeemed_by_user_id": None},
            {
                "$set": {
                    "redeemed_by_user_id": to_object_id(user_id, field_name="user_id"),
                    "redeemed_at": now,
                    "redemption_outcome": outcome,
                    "updated_at": now,
                }
            },
        )
        return result.modified_count == 1


def _hydrate(row: dict[str, Any]) -> StoredSubscription:
    price = None
    if row.get("price_minor") is not None and row.get("currency"):
        price = Money(int(row["price_minor"]), Currency(row["currency"]))
    return StoredSubscription(
        id=row["_id"],
        user_id=str(row["user_id"]),
        state=SubscriptionState(
            plan=PlanId(row["plan"]),
            region=BillingRegion(row["region"]),
            status=SubscriptionStatus(row["status"]),
            period_start=row["period_start"],
            period_end=row["period_end"],
            renewal_failed_at=row.get("renewal_failed_at"),
            failure_reason=(
                PaymentFailureReason(row["failure_reason"]) if row.get("failure_reason") else None
            ),
            mandate_retry_required=bool(row.get("mandate_retry_required")),
            founding=bool(row.get("founding")),
        ),
        provider=PaymentProviderName(row["provider"]),
        price=price,
        provider_sub_id=row.get("provider_sub_id"),
    )


def _hydrate_gift(row: dict[str, Any]) -> Gift:
    return Gift(
        code=row["code"],
        buyer_user_id=str(row["buyer_user_id"]),
        plan=PlanId(row["plan"]),
        region=BillingRegion(row["region"]),
        value=Money(int(row["value_minor"]), Currency(row["currency"])),
        term_days=int(row["term_days"]),
        purchased_at=row["created_at"],
        expires_at=row["expires_at"],
        redeemed_by_user_id=(
            str(row["redeemed_by_user_id"]) if row.get("redeemed_by_user_id") else None
        ),
        redeemed_at=row.get("redeemed_at"),
    )
