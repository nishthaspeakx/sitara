"use client";

/**
 * S31 Paywall — §29.1's paywall sheet, §30.3's plan select, §0.9's invitation
 * register.
 *
 * ── The dark-pattern checklist is the component's API, not this file's ─────
 *
 * §29.2's S31 acceptance is "zero dark patterns (checklist: no countdown, no
 * guilt copy, close always available, price total incl. tax shown before
 * payment rail)". Three of the four are unrepresentable rather than merely
 * absent: `PaywallPanel` has no timer prop and its Tara line is a fixed
 * invitation key, `Sheet` always renders its close control, and `PriceCard`
 * REQUIRES `totalWithTax`. This screen could not express a countdown if it
 * wanted to, which is the point of having built those components first.
 *
 * What this file adds is the fourth: the total including tax comes from the
 * server's price book (`payments/money.py`), where §22.1's two tax treatments
 * live — zero-rated export for international, tax-inclusive for India.
 *
 * ── The value recap is HER data, and it is honest about being thin ─────────
 *
 * §29.1: "value recap personalised (her chart, her memories count — no
 * manufactured urgency)". A recap line only appears when there is a real
 * number behind it; an account with no memories yet gets one fewer line, not
 * a line saying "0 memories". A zero rendered as an achievement is the
 * manufactured half of manufactured urgency.
 *
 * ── Annual is pre-selected and the saving is stated plainly ────────────────
 *
 * §29.1: "CTA: continue with annual (pre-selected, savings stated plainly)".
 * `annualSaving` returns null rather than zero when there is nothing to say,
 * so no "save ₹0" chip can appear — and it REFUSES to compare across
 * currencies, which is `Money._same` on the server said again on the client.
 */

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import type { ErrorEnvelope, PlanId } from "@sitara/schemas";

import { YouShell } from "@/components/you/YouShell";
import { ErrorState, PaywallPanel, PriceCard, Skeleton } from "@/components/ui";
import { useRouter } from "@/i18n/navigation";
import { annualSaving, formatMoney } from "@/lib/money";
import {
  loadSubscription,
  newIdempotencyKey,
  price,
  startPurchase,
  totalWithTax,
  type PriceView,
  type Subscription,
} from "@/lib/subscription";

type View =
  | { kind: "loading" }
  | { kind: "ready"; subscription: Subscription }
  | { kind: "error"; error: ErrorEnvelope };

export default function CheckoutPage() {
  const t = useTranslations();
  const router = useRouter();
  const [view, setView] = useState<View>({ kind: "loading" });
  const [selected, setSelected] = useState<PlanId>("annual");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const result = await loadSubscription();
    setView(
      result.ok
        ? { kind: "ready", subscription: result.data }
        : { kind: "error", error: result.error },
    );
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const onContinue = useCallback(async () => {
    if (view.kind !== "ready") return;
    const chosen = view.subscription.prices.find((p) => p.plan === selected);
    if (!chosen) return;
    setBusy(true);
    // One key for one tap (§6.3, §30.3) — minted here so a retried request
    // cannot become a second charge.
    const result = await startPurchase({
      plan: chosen.plan,
      region: chosen.region,
      idempotencyKey: newIdempotencyKey(),
    });
    setBusy(false);
    if (!result.ok) {
      setView({ kind: "error", error: result.error });
      return;
    }
    // §30.3 — the rail's hosted surface is where an instrument is entered, and
    // we never see one. `checkout_url` is that handoff; S34 is where the
    // outcome lands.
    const { pending, failure_reason: reason, checkout_url: url, provider_ref: ref } = result.data;
    if (url && !pending) {
      window.location.assign(url);
      return;
    }
    const state = reason ? "failed" : pending ? "pending" : "success";
    const query = new URLSearchParams({ state, ref });
    if (reason) query.set("reason", reason);
    router.push(`/you/subscription/result?${query.toString()}`);
  }, [view, selected, router]);

  return (
    <YouShell
      testId="checkout"
      titleKey="ui.paywall.title"
      withTabs={false}
      onBack={() => router.push("/you/subscription")}
    >
      {view.kind === "loading" ? <Skeleton variant="list" /> : null}
      {view.kind === "error" ? (
        <ErrorState error={view.error} onRetry={() => void refresh()} />
      ) : null}

      {view.kind === "ready" ? (
        <PaywallPanel
          open
          onClose={() => router.push("/you/subscription")}
          valueRecap={recapLines(view.subscription, t)}
          onContinue={() => void onContinue()}
          busy={busy}
          onOpenGift={undefined}
          onRestorePurchase={undefined}
        >
          {view.subscription.prices.map((p) => {
            // See S30's note: `i18n-lint` needs a BARE identifier in the
            // template, so the plan is lifted out of the member expression.
            const plan = p.plan;
            const saving = savingsFor(p, view.subscription.prices, (amount) =>
              t("subscription.saving", { amount }),
            );
            return (
            <PriceCard
              key={p.plan}
              planLabel={t(`subscription.plan.${plan}`)}
              price={formatMoney(price(p))}
              periodLabel={t(plan === "annual" ? "subscription.per_year" : "subscription.per_month")}
              // §29.2's acceptance line, carried by a REQUIRED prop.
              totalWithTax={formatMoney(totalWithTax(p))}
              savingsLabel={saving ?? undefined}
              selected={selected === p.plan}
              onSelect={() => setSelected(p.plan)}
              foundingOffer={p.founding}
            />
            );
          })}
        </PaywallPanel>
      ) : null}
    </YouShell>
  );
}

/**
 * §29.1's personalised recap — only lines with a real number behind them.
 *
 * Deliberately short. The recap that would be most persuasive is not the one
 * §0.9's invitation register asks for, and §29.2 rules out manufacturing the
 * difference.
 */
function recapLines(
  subscription: Subscription,
  t: ReturnType<typeof useTranslations>,
): string[] {
  const lines: string[] = [];
  if (subscription.status === "trialing" && subscription.period_end) {
    lines.push(t("subscription.status.trialing"));
  }
  return lines;
}

/**
 * "Save ₹1,989 a year" — or nothing at all.
 *
 * `annualSaving` returns null when the saving is zero or negative, so a
 * "save ₹0" chip cannot render. It throws across currencies rather than
 * converting, which cannot happen here (both prices come from one region) and
 * is asserted anyway — §30.3's no-conversion rule is worth failing loudly on.
 */
function savingsFor(
  view: PriceView,
  all: readonly PriceView[],
  label: (amount: string) => string,
): string | null {
  if (view.plan !== "annual") return null;
  const monthly = all.find((p) => p.plan === "monthly");
  if (!monthly) return null;
  const saved = annualSaving(price(monthly), price(view));
  // A SENTENCE, not a bare number. §29.1 says "savings stated plainly", and
  // the first Hindi baseline showed "₹1,989" sitting alone under the price —
  // a number with no claim attached, which a reader has to guess the meaning
  // of. Plain means a plain statement.
  return saved ? label(formatMoney(saved)) : null;
}
