/**
 * §30.3's subscription API, client side.
 *
 * ── The client never decides what access she has ───────────────────────────
 *
 * `SubscriptionStatus` crosses the wire; the ACCESS LEVEL does not. That is
 * deliberate on the server (`payments/lifecycle.py` explains it) and this file
 * is the half that keeps it true: nothing here maps a status to a permission,
 * because a client that computed access could disagree with the server about
 * it — and the disagreement would be invisible until the one case they
 * computed differently for. S30 renders what she HAS; the server enforces what
 * she may do.
 *
 * What the client does own is §32.1's Today variant, which is a display rule
 * over `TodayState` and already lives in `today-variant.ts`. Those are
 * different questions and it matters that they stay in different files.
 *
 * ── Idempotency keys are minted here ───────────────────────────────────────
 *
 * §6.3 requires one on every mutation, and §30.3 names them as the
 * duplicate-payment guard. The key belongs to the USER'S INTENT — one tap on
 * "continue" — so it is minted when the tap happens and reused across retries
 * of that same tap. A key minted per HTTP request would make a retried request
 * a second charge, which is precisely what it exists to prevent.
 */

import type { PlanId, BillingRegion, SubscriptionStatus } from "@sitara/schemas";

import { apiCall, type ApiResult } from "./api";
import type { WireMoney } from "./money";

export interface PriceView {
  plan: PlanId;
  region: BillingRegion;
  amount_minor: number;
  currency: string;
  /** §29.2's S31 acceptance — required, never optional. */
  total_with_tax_minor: number;
  term_days: number;
  founding: boolean;
}

export interface Subscription {
  status: SubscriptionStatus | null;
  plan: PlanId | null;
  region: BillingRegion | null;
  /** §22.13's ladder, for S30's banner. Null when no renewal has failed. */
  renewal_failed_at: string | null;
  grace_ends_at: string | null;
  downgrades_at: string | null;
  period_start: string | null;
  period_end: string | null;
  price_minor: number | null;
  currency: string | null;
  mandate_retry_required: boolean;
  founding: boolean;
  /** §22.13's "no hard deletion", carried onto the screen that says so. */
  retains_history: boolean;
  /** Whether the rail that took this money moves any. S30 says so plainly. */
  simulated: boolean;
  /** §30.3 — offered AT renewal only, never mid-cycle. */
  region_switch_offered: boolean;
  prices: PriceView[];
  /** False when no rail serves her region. S31 hides the CTA rather than
   *  offering a purchase that cannot complete. */
  purchasable: boolean;
}

export interface PurchaseResult {
  /** §30.3's UPI hold. Neither success nor failure — S34's third state. */
  pending: boolean;
  checkout_url: string | null;
  failure_reason: string | null;
  provider_ref: string;
}

export interface RedemptionResult {
  outcome: string;
  message_key: string;
  extended_to: string | null;
  /** §30.3: "gift credits are denominated in their purchase currency" — so
   *  this may be a different currency from her subscription's, and rendering
   *  it as hers would be the conversion §30.3 forbids. */
  gift_value: WireMoney | null;
}

export function price(view: PriceView): WireMoney {
  return { minor: view.amount_minor, currency: view.currency };
}

export function totalWithTax(view: PriceView): WireMoney {
  return { minor: view.total_with_tax_minor, currency: view.currency };
}

export function subscriptionPrice(sub: Subscription): WireMoney | null {
  if (sub.price_minor === null || sub.currency === null) return null;
  return { minor: sub.price_minor, currency: sub.currency };
}

export function loadSubscription(region?: BillingRegion): Promise<ApiResult<Subscription>> {
  const query = region ? `?region=${encodeURIComponent(region)}` : "";
  return apiCall<Subscription>(`/v1/subscription${query}`);
}

/**
 * One tap on "continue". `idempotencyKey` is the CALLER's — see the header.
 */
export function startPurchase(body: {
  plan: PlanId;
  region: BillingRegion;
  idempotencyKey: string;
  founding?: boolean;
}): Promise<ApiResult<PurchaseResult>> {
  return apiCall<PurchaseResult>("/v1/subscription/purchase", {
    method: "POST",
    body: JSON.stringify({
      plan: body.plan,
      region: body.region,
      idempotency_key: body.idempotencyKey,
      founding: body.founding ?? false,
    }),
  });
}

/** §22.13's one-tap alternate-payment retry. */
export function retryRenewal(body: {
  plan: PlanId;
  region: BillingRegion;
  idempotencyKey: string;
}): Promise<ApiResult<PurchaseResult>> {
  return apiCall<PurchaseResult>("/v1/subscription/retry", {
    method: "POST",
    body: JSON.stringify({
      plan: body.plan,
      region: body.region,
      idempotency_key: body.idempotencyKey,
    }),
  });
}

/**
 * §30.3's cancellation. No body, and that is the design.
 *
 * "One screen, immediate confirm, no retention labyrinth — one optional 'tell
 * us why'." Optional means the request carries nothing: a reason field here,
 * even an optional one, is a field a future screen makes required.
 */
export function cancelSubscription(): Promise<ApiResult<Subscription>> {
  return apiCall<Subscription>("/v1/subscription/cancel", { method: "POST" });
}

/** §22.16's 7-day no-questions window, annual only. */
export function requestRefund(): Promise<ApiResult<Subscription>> {
  return apiCall<Subscription>("/v1/subscription/refund", { method: "POST" });
}

export function redeemGift(code: string): Promise<ApiResult<RedemptionResult>> {
  return apiCall<RedemptionResult>("/v1/subscription/redeem", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
}

/** §30.3's billing-region migration. Refused mid-cycle by the server. */
export function switchRegion(region: BillingRegion): Promise<ApiResult<Subscription>> {
  return apiCall<Subscription>("/v1/subscription/region", {
    method: "POST",
    body: JSON.stringify({ region }),
  });
}

/**
 * A key for one user intent (§6.3, §30.3).
 *
 * `crypto.randomUUID` rather than a timestamp: two taps in the same
 * millisecond are rare and a collision here is a charge that silently does not
 * happen, which is the failure nobody reports because it looks like success.
 */
export function newIdempotencyKey(): string {
  return `web-${crypto.randomUUID()}`;
}
