"""Subscription endpoints (§30.3, S30/S31/S34).

Thin on purpose, like `today/router.py`: every decision is made somewhere
better, and the router's job is to turn a session into a user id, call one
service method, and serialise. What it adds is the §34.4 envelope and the §6.3
status convention.

── Money crosses in MINOR UNITS, never as a formatted string ───────────────

§2.3 gives INR Indian digit grouping (₹1,45,000) and USD Western grouping, and
CC-013 fixes Latin numerals in every locale. All three are locale-aware
FORMATTING decisions, and they are made on the client beside `Intl`
(`apps/web/src/lib/money.ts`). A server that sent "₹499" would have chosen a
grouping for a locale it was only guessing at — and one that sent 499.0 would
have chosen a rounding.

── What is NOT here ────────────────────────────────────────────────────────

**No endpoint returns a rail name.** §30.3 puts collection behind a hosted
surface, and a client that knew which rail answered is a client that could
branch on it. `simulated` IS returned, because a prototype whose receipts are
indistinguishable from real ones is a prototype somebody eventually shows to a
customer — but that is a boolean about the deployment, not a vendor.

**No endpoint mutates the region mid-cycle.** `POST /region` calls straight
into `lifecycle.migrate_region`, which raises rather than deferring, and the
refusal surfaces as a 422. §30.3's rule is about the instant, not the intent.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sitara_schemas import ErrorCode
from sitara_schemas.payments import BillingRegion, PlanId

from sitara_api.auth.router import CurrentSession
from sitara_api.errors import ApiError
from sitara_api.payments.lifecycle import MigrationRefused
from sitara_api.payments.money import NoSuchPrice, price_for
from sitara_api.payments.providers.base import PaymentProviderUnavailable
from sitara_api.payments.providers.routing import purchases_available_in, resolve
from sitara_api.payments.service import (
    NoSubscription,
    PaymentService,
    RefundWindowClosed,
    SubscriptionView,
)

router = APIRouter(prefix="/v1/subscription", tags=["subscription"])


class PriceView(BaseModel):
    """One PriceCard's data. §29.2's acceptance is in the REQUIRED fields.

    `total_with_tax` is not optional, because `PriceCard` will not render
    without it — §30.3's acceptance line ("price total incl. tax shown before
    payment rail") is carried by the type rather than by a reviewer noticing.
    """

    plan: PlanId
    region: BillingRegion
    amount_minor: int
    currency: str
    total_with_tax_minor: int
    term_days: int
    founding: bool = False


class SubscriptionResponse(BaseModel):
    status: str | None
    plan: str | None
    region: str | None
    #: §22.13's ladder, for S30's banner. Nulls when no renewal has failed.
    renewal_failed_at: dt.datetime | None = None
    grace_ends_at: dt.datetime | None = None
    downgrades_at: dt.datetime | None = None
    period_start: dt.datetime | None = None
    period_end: dt.datetime | None = None
    price_minor: int | None = None
    currency: str | None = None
    mandate_retry_required: bool = False
    founding: bool = False
    retains_history: bool = True
    simulated: bool = False
    region_switch_offered: bool = False
    #: The plans she may buy right now, in her billing region.
    prices: list[PriceView] = Field(default_factory=list)
    #: False when no rail serves her region (§30.3). S31 hides the CTA rather
    #: than offering a purchase that cannot complete.
    purchasable: bool = True


class PurchaseRequestBody(BaseModel):
    plan: PlanId
    region: BillingRegion
    #: §6.3 — idempotency keys on all mutation endpoints. Client-generated so
    #: a retried request cannot become a second charge.
    idempotency_key: str = Field(min_length=8, max_length=128)
    founding: bool = False


class PurchaseResponse(BaseModel):
    """S34's three states, as one shape.

    `checkout_url` is where the user goes to enter an instrument we never see.
    `pending` is §30.3's UPI hold and is neither success nor failure.
    """

    pending: bool
    checkout_url: str | None
    failure_reason: str | None = None
    provider_ref: str


class RedeemRequestBody(BaseModel):
    code: str = Field(min_length=4, max_length=64)


class RegionRequestBody(BaseModel):
    region: BillingRegion


def _service(request: Request) -> PaymentService:
    service = getattr(request.app.state, "payments", None)
    if service is None:
        raise ApiError(ErrorCode.SYS_UNAVAILABLE, "errors.sys.unavailable")
    return service


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _render(view: SubscriptionView, *, region: BillingRegion) -> SubscriptionResponse:
    return SubscriptionResponse(
        status=view.status.value if view.status else None,
        plan=view.plan.value if view.plan else None,
        region=view.region.value if view.region else None,
        renewal_failed_at=view.renewal_failed_at,
        grace_ends_at=view.grace_ends_at,
        downgrades_at=view.downgrades_at,
        period_start=view.period_start,
        period_end=view.period_end,
        price_minor=view.price.minor if view.price else None,
        currency=view.price.currency.value if view.price else None,
        mandate_retry_required=view.mandate_retry_required,
        founding=view.founding,
        retains_history=view.retains_history,
        simulated=view.simulated,
        region_switch_offered=view.region_switch_offered,
        prices=_prices_for(region),
        purchasable=purchases_available_in(region),
    )


def _prices_for(region: BillingRegion) -> list[PriceView]:
    views: list[PriceView] = []
    for plan in (PlanId.MONTHLY, PlanId.ANNUAL):
        price = price_for(region, plan)
        views.append(
            PriceView(
                plan=plan,
                region=region,
                amount_minor=price.amount.minor,
                currency=price.amount.currency.value,
                total_with_tax_minor=price.total_with_tax.minor,
                term_days=price.term_days,
            )
        )
    return views


@router.get("")
async def read_subscription(
    request: Request, session: CurrentSession, region: BillingRegion = BillingRegion.INDIA
) -> SubscriptionResponse:
    """S30's payload. Projects §22.13's clock — see `service.read`."""
    user_id, _ = session
    view = await _service(request).read(user_id=str(user_id), now=_now())
    return _render(view, region=view.region or region)


@router.post("/purchase")
async def purchase(
    body: PurchaseRequestBody, request: Request, session: CurrentSession
) -> PurchaseResponse:
    """§30.3's plan-select → rail handoff. Grants nothing (see the service)."""
    user_id, _ = session
    route = resolve(body.region)
    if not route.available:
        # §30.3's gap, made a runtime state rather than a silent fallback.
        raise ApiError(ErrorCode.PAY_RAIL_UNAVAILABLE, route.reason_key or "errors.pay.rail")
    try:
        handle = await _service(request).start_purchase(
            user_id=str(user_id),
            plan=body.plan,
            region=body.region,
            idempotency_key=body.idempotency_key,
            now=_now(),
            founding=body.founding,
        )
    except NoSuchPrice as exc:
        raise ApiError(ErrorCode.SYS_VALIDATION, "errors.pay.no_such_price") from exc
    except PaymentProviderUnavailable as exc:
        raise ApiError(ErrorCode.PAY_PROVIDER_ERROR, "errors.pay.provider") from exc
    return PurchaseResponse(
        pending=handle.pending,
        checkout_url=handle.checkout_url,
        failure_reason=handle.failure_reason.value if handle.failure_reason else None,
        provider_ref=handle.provider_ref,
    )


@router.post("/cancel")
async def cancel(request: Request, session: CurrentSession) -> SubscriptionResponse:
    """§30.3: one screen, immediate confirm, no retention labyrinth.

    There is deliberately no "reason" REQUIRED anywhere in this signature.
    §30.3 allows "one optional 'tell us why'", and a required field would make
    the cancellation conditional on answering a question — which is the
    labyrinth by another name.
    """
    user_id, _ = session
    view = await _service(request).cancel(user_id=str(user_id), now=_now())
    return _render(view, region=view.region or BillingRegion.INDIA)


@router.post("/retry")
async def retry(
    body: PurchaseRequestBody, request: Request, session: CurrentSession
) -> PurchaseResponse:
    """§22.13's one-tap alternate-payment retry."""
    user_id, _ = session
    try:
        handle = await _service(request).retry_renewal(
            user_id=str(user_id), idempotency_key=body.idempotency_key, now=_now()
        )
    except NoSubscription as exc:
        raise ApiError(ErrorCode.PAY_PAYMENT_REQUIRED, "errors.pay.no_subscription") from exc
    except PaymentProviderUnavailable as exc:
        raise ApiError(ErrorCode.PAY_PROVIDER_ERROR, "errors.pay.provider") from exc
    return PurchaseResponse(
        pending=handle.pending,
        checkout_url=handle.checkout_url,
        failure_reason=handle.failure_reason.value if handle.failure_reason else None,
        provider_ref=handle.provider_ref,
    )


@router.post("/refund")
async def refund(request: Request, session: CurrentSession) -> SubscriptionResponse:
    """§22.16's 7-day no-questions window, annual only."""
    user_id, _ = session
    try:
        view = await _service(request).refund(user_id=str(user_id), now=_now())
    except NoSubscription as exc:
        raise ApiError(ErrorCode.PAY_PAYMENT_REQUIRED, "errors.pay.no_subscription") from exc
    except RefundWindowClosed as exc:
        raise ApiError(
            ErrorCode.PAY_REFUND_WINDOW_CLOSED, "errors.pay.refund_window_closed"
        ) from exc
    return _render(view, region=view.region or BillingRegion.INDIA)  # type: ignore[arg-type]


@router.post("/redeem")
async def redeem(
    body: RedeemRequestBody, request: Request, session: CurrentSession
) -> dict[str, Any]:
    """§30.3's S33, all five outcomes.

    A refusal is a 422 with ONE message key for expired, used and unknown — a
    response that distinguished them is an oracle for enumerating gift codes,
    and §30.3 gives all three the same warm error anyway. The OUTCOME is
    returned so the client can log it; the message is what she reads.
    """
    user_id, _ = session
    redemption = await _service(request).redeem_gift(
        user_id=str(user_id), code=body.code, now=_now()
    )
    if not redemption.succeeded:
        raise ApiError(ErrorCode.PAY_GIFT_UNREDEEMABLE, redemption.message_key)
    return {
        "outcome": redemption.outcome.value,
        "message_key": redemption.message_key,
        "extended_to": redemption.extended_to,
        # §30.3: "gift credits are denominated in their purchase currency."
        # Reported in the GIFT's currency, which may not be hers.
        "gift_value": redemption.gift_value.as_wire() if redemption.gift_value else None,
    }


@router.post("/region")
async def change_region(
    body: RegionRequestBody, request: Request, session: CurrentSession
) -> SubscriptionResponse:
    """§30.3's billing-region migration, offered at renewal and refused before.

    422, not 409: the request is well formed and the caller is entitled to make
    it — what fails is a domain rule about WHEN, which is §6.3's 422.
    """
    user_id, _ = session
    try:
        view = await _service(request).migrate_region(
            user_id=str(user_id), region=body.region, now=_now()
        )
    except NoSubscription as exc:
        raise ApiError(ErrorCode.PAY_PAYMENT_REQUIRED, "errors.pay.no_subscription") from exc
    except MigrationRefused as exc:
        raise ApiError(ErrorCode.SYS_VALIDATION, "errors.pay.migration_mid_cycle") from exc
    return _render(view, region=body.region)
