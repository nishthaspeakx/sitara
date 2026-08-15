"""The simulator's control surface — dev only (§30.3).

    POST /v1/dev/payments/arm      {"fault": "fail_renewal"}
    POST /v1/dev/payments/approve  {"provider_ref": "..."}     ← the hosted page
    POST /v1/dev/payments/advance  {"days": 8}                 ← move the clock
    POST /v1/dev/payments/gift     {"to_existing": true}
    GET  /v1/dev/payments/state

This is what makes the milestone demonstrable by hand: "fail the next
renewal", "expire the grace period", "gift to an existing subscriber" are each
one call, and every one of them drives the REAL service through the REAL state
machine. Nothing here is a shortcut past the code the demo is showing.

── Three rules it does not break ───────────────────────────────────────────

**1. It is mounted only in dev.** `app.py` gates it on `environment == "dev"`,
the same gate `db.seed`, the local CSFLE KMS and `daily_guidance.dev_router`
all sit behind. A control surface that can grant paid access is not one to
leave reachable.

**2. It goes THROUGH `verify_webhook`.** `/approve` signs a payload and posts
it the way a rail would, rather than calling `handle_event` directly. A control
surface that called past the signature check would leave the one security
property of the webhook path (§13) unexercised by every demo ever run — which
is precisely the property that most wants exercising, since it is what stands
between a forged POST and free paid access.

**3. It never touches a release gate.** `release_gates.py` does not import this
module, and `payments.live_rails` reads the capability matrix, which nothing
here writes. §30.3's rails stay DECLARED however much of the flow gets
demonstrated — the same rule `prototype.py` states about §33.5.

── Why `advance` moves a STORED clock and not the process clock ────────────

"Expire the grace period" needs the subscription to believe eight days have
passed. The two honest ways are to move the row backwards or to move the
reader's clock forwards; monkeypatching `datetime.now` process-wide would move
it for §7.1's brief scheduler and §32.13's date binding too, and a demo whose
morning brief silently regenerated for a different day would be demonstrating
a bug that is not there. So this shifts the row's OWN timestamps, which is
exactly what a subscription eight days further along looks like.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sitara_schemas import ErrorCode
from sitara_schemas.payments import BillingRegion, PaymentFailureReason, PlanId

from sitara_api.auth.router import CurrentSession
from sitara_api.chat_orchestration.store import to_object_id
from sitara_api.errors import ApiError
from sitara_api.payments.providers.simulator import Fault, SimulatedRail
from sitara_api.payments.service import PaymentService

router = APIRouter(prefix="/v1/dev/payments", tags=["dev"])

#: The row fields §22.13's clock is measured against. Shifting all of them by
#: the same delta is what "N days later" means for a subscription — shifting
#: only some would produce a state no real subscription can be in, and the
#: demo would be showing a screen the product cannot actually reach.
_CLOCK_FIELDS = ("created_at", "period_start", "period_end", "renewal_failed_at")


class ArmBody(BaseModel):
    fault: Fault
    reason: PaymentFailureReason = PaymentFailureReason.INSUFFICIENT_FUNDS
    sticky: bool = False


class ApproveBody(BaseModel):
    provider_ref: str


class AdvanceBody(BaseModel):
    """Negative days are not offered. §22.13's ladder only runs forwards, and a
    control that could run it backwards would let a demo show a recovery that
    the product has no path to."""

    days: int = Field(gt=0, le=400)


class GiftBody(BaseModel):
    plan: PlanId = PlanId.ANNUAL
    region: BillingRegion = BillingRegion.INTERNATIONAL


def _service(request: Request) -> PaymentService:
    service = getattr(request.app.state, "payments", None)
    if service is None:
        raise ApiError(ErrorCode.SYS_UNAVAILABLE, "errors.sys.unavailable")
    return service


def _rail(request: Request) -> SimulatedRail:
    rail = getattr(request.app.state, "payment_rail", None)
    if not isinstance(rail, SimulatedRail):
        # The control surface only controls the simulator. If a real rail is
        # wired, this refuses rather than doing something approximate — there
        # is no "arm a fault" on Razorpay, and pretending otherwise would let a
        # demo claim to have shown a state it never reached.
        raise ApiError(ErrorCode.SYS_UNAVAILABLE, "errors.pay.not_simulated")
    return rail


@router.get("/state")
async def state(request: Request, session: CurrentSession) -> dict[str, Any]:
    """What the rail is about to do, and what she currently has."""
    user_id, _ = session
    rail = _rail(request)
    view = await _service(request).read(user_id=str(user_id), now=dt.datetime.now(dt.UTC))
    return {
        "armed": rail.armed.value if rail.armed else None,
        "faults": [fault.value for fault in Fault],
        "status": view.status.value if view.status else None,
        "access": view.access.value,
        "plan_state": view.plan_state.value,
        "period_end": view.period_end,
        "grace_ends_at": view.grace_ends_at,
        "downgrades_at": view.downgrades_at,
    }


@router.post("/arm")
async def arm(body: ArmBody, request: Request, session: CurrentSession) -> dict[str, Any]:
    """"Fail the next renewal", and its four siblings."""
    rail = _rail(request)
    rail.arm(body.fault, reason=body.reason, sticky=body.sticky)
    return {"armed": body.fault.value, "sticky": body.sticky}


@router.post("/disarm")
async def disarm(request: Request, session: CurrentSession) -> dict[str, Any]:
    _rail(request).disarm()
    return {"armed": None}


@router.post("/approve")
async def approve(
    body: ApproveBody, request: Request, session: CurrentSession
) -> dict[str, Any]:
    """The hosted rail page, standing in for itself.

    Signs a delivery and pushes it through `verify_webhook` — see rule 2 in the
    module header. This is the one endpoint whose whole point is that it takes
    the long way round.
    """
    rail = _rail(request)
    service = _service(request)
    now = dt.datetime.now(dt.UTC)
    payload, signature = rail.sign(
        {
            "provider_event_id": f"sim_evt_{body.provider_ref}",
            "provider_ref": body.provider_ref,
            "kind": "payment.succeeded",
            "idempotency_key": body.provider_ref,
            "amount": None,
            "occurred_at": now.isoformat(),
        }
    )
    event = rail.verify_webhook(payload=payload, signature=signature)
    outcome = await service.handle_event(event, now=now)
    return {
        "applied": outcome.applied,
        "duplicate": outcome.duplicate,
        "refunded_duplicate": outcome.refunded_duplicate,
    }


@router.post("/renewal-failed")
async def renewal_failed(
    body: ArmBody, request: Request, session: CurrentSession
) -> dict[str, Any]:
    """§22.13's grace, started directly — the demo's "fail this renewal now"."""
    user_id, _ = session
    view = await _service(request).record_renewal_failure(
        user_id=str(user_id), reason=body.reason, now=dt.datetime.now(dt.UTC)
    )
    return {"status": view.status.value if view.status else None, "access": view.access.value}


@router.post("/mandate-rejected")
async def mandate_rejected(request: Request, session: CurrentSession) -> dict[str, Any]:
    """§30.3's post-purchase rejection: active on the paid period."""
    user_id, _ = session
    view = await _service(request).record_mandate_rejected(
        user_id=str(user_id), now=dt.datetime.now(dt.UTC)
    )
    return {
        "status": view.status.value if view.status else None,
        "mandate_retry_required": view.mandate_retry_required,
    }


@router.post("/advance")
async def advance(
    body: AdvanceBody, request: Request, session: CurrentSession
) -> dict[str, Any]:
    """"Expire the grace period" — moves the ROW, not the process clock.

    See the module header for why. Every §22.13 timestamp shifts by the same
    delta, so the row lands in a state a real subscription reaches by waiting.
    """
    user_id, _ = session
    db = request.app.state.db
    delta = dt.timedelta(days=body.days)
    row = await db.subscriptions.find_one(
        {"user_id": to_object_id(str(user_id), field_name="user_id"), "live": True}
    )
    if row is None:
        raise ApiError(ErrorCode.PAY_PAYMENT_REQUIRED, "errors.pay.no_subscription")
    shifted = {
        field: row[field] - delta
        for field in _CLOCK_FIELDS
        if row.get(field) is not None
    }
    await db.subscriptions.update_one({"_id": row["_id"]}, {"$set": shifted})

    # Read it back through the REAL service, so what the demo sees is what
    # §22.13's projection actually computes rather than what this endpoint
    # believes it did.
    view = await _service(request).read(user_id=str(user_id), now=dt.datetime.now(dt.UTC))
    return {
        "days": body.days,
        "status": view.status.value if view.status else None,
        "access": view.access.value,
        "plan_state": view.plan_state.value,
    }


@router.post("/gift")
async def gift(body: GiftBody, request: Request, session: CurrentSession) -> dict[str, Any]:
    """"Gift to an existing subscriber", end to end.

    Buys a gift as somebody else and redeems it as the signed-in user, so the
    branch it exercises depends on whether she already has a subscription —
    which is the point. §30.3's credit conversion is the interesting half and
    it is not reachable any other way from a single account.
    """
    user_id, _ = session
    service = _service(request)
    now = dt.datetime.now(dt.UTC)
    purchased = await service.purchase_gift(
        # The buyer is the signed-in user's own id here only because a demo has
        # one account. §22.1 makes the gift a sale to the BUYER's region, which
        # `body.region` carries — and §10-20's NRI case (buy USD, redeem India)
        # is the default precisely because it is the interesting one.
        buyer_user_id=str(user_id),
        plan=body.plan,
        region=body.region,
        idempotency_key=f"dev-gift-{now.timestamp()}",
        now=now,
    )
    redemption = await service.redeem_gift(user_id=str(user_id), code=purchased.code, now=now)
    view = await service.read(user_id=str(user_id), now=now)
    return {
        "code": purchased.code,
        "outcome": redemption.outcome.value,
        "gift_value": redemption.gift_value.as_wire() if redemption.gift_value else None,
        "period_end": view.period_end,
        # §30.3: her subscription keeps its OWN currency. A USD gift extending
        # an INR subscription is the assertion worth watching on screen.
        "subscription_currency": view.price.currency.value if view.price else None,
    }


@router.post("/reset")
async def reset(request: Request, session: CurrentSession) -> dict[str, Any]:
    """Back to no subscription at all, for the next run of the walkthrough.

    Deletes the demo account's own rows and nothing else — scoped by user id,
    never a collection drop, because a dev database is also where somebody
    else's half-finished work lives.
    """
    user_id, _ = session
    oid = to_object_id(str(user_id), field_name="user_id")
    db = request.app.state.db
    subscriptions = await db.subscriptions.delete_many({"user_id": oid})
    payments = await db.payments.delete_many({"user_id": oid})
    gifts = await db.gifts.delete_many({"buyer_user_id": oid})
    _rail(request).disarm()
    return {
        "subscriptions": subscriptions.deleted_count,
        "payments": payments.deleted_count,
        "gifts": gifts.deleted_count,
    }
