"use client";

/**
 * S32 — gift flow (§29.1 `/you/gift`, §30.3's gifting rules, §25/§27).
 *
 * ── There is no recipient field, and that is the design ────────────────────
 *
 * A gift is a BEARER INSTRUMENT: the buyer pays, gets a code, and passes it on
 * however they like. Taking an email or a phone number here would turn this
 * screen into one that MESSAGES a third party on a user's behalf — a §23
 * notification, carrying a §23.5 consent question, addressed to somebody who
 * has no account and has agreed to nothing. `purchaseGift` has no parameter
 * for one and neither does the route, so this is a shape rather than a
 * restraint.
 *
 * ── The gift's money is the GIFT's, not the buyer's future subscription's ──
 *
 * §22.1 makes this a sale to the BUYER's region, which fixes its currency and
 * its rail. That has nothing to do with where it is redeemed — §10-20's NRI
 * case is precisely the two differing — and `lifecycle.extend` is what keeps
 * §30.3's "retains its original currency" and "a USD gift extends an INR
 * subscription" true at once, by granting DAYS. Nothing on this screen
 * converts anything.
 *
 * ── No dark patterns, same checklist as S31 ────────────────────────────────
 *
 * No countdown, no guilt copy, no "they'll be so disappointed". The saving on
 * the annual card is stated plainly by the same helper S31 uses, and it cannot
 * render a zero.
 */

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import type { ErrorEnvelope, PlanId } from "@sitara/schemas";

import { YouShell } from "@/components/you/YouShell";
import { Button, Card, ErrorState, PriceCard, Skeleton } from "@/components/ui";
import { useRouter } from "@/i18n/navigation";
import { formatMoney } from "@/lib/money";
import {
  loadSubscription,
  newIdempotencyKey,
  price,
  purchaseGift,
  totalWithTax,
  type GiftResult,
  type Subscription,
} from "@/lib/subscription";

type View =
  | { kind: "loading" }
  | { kind: "ready"; subscription: Subscription }
  | { kind: "bought"; gift: GiftResult }
  | { kind: "error"; error: ErrorEnvelope };

export default function GiftPage() {
  const t = useTranslations();
  const router = useRouter();
  const [view, setView] = useState<View>({ kind: "loading" });
  const [selected, setSelected] = useState<PlanId>("annual");
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

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

  const onBuy = useCallback(async () => {
    if (view.kind !== "ready") return;
    const chosen = view.subscription.prices.find((p) => p.plan === selected);
    if (!chosen) return;
    setBusy(true);
    // One key for one tap (§6.3, §30.3) — a retried request must not mint a
    // second gift, which would be a second charge with a second code.
    const result = await purchaseGift({
      plan: chosen.plan,
      region: chosen.region,
      idempotencyKey: newIdempotencyKey(),
    });
    setBusy(false);
    setView(
      result.ok
        ? { kind: "bought", gift: result.data }
        : { kind: "error", error: result.error },
    );
  }, [view, selected]);

  return (
    <YouShell
      testId="gift"
      titleKey="gift.title"
      withTabs={false}
      onBack={() => router.push("/you/subscription")}
    >
      {view.kind === "loading" ? <Skeleton variant="list" /> : null}
      {view.kind === "error" ? (
        <ErrorState error={view.error} onRetry={() => void refresh()} />
      ) : null}

      {view.kind === "ready" ? (
        <div className="flex flex-col gap-4">
          <p className="text-body text-ink-secondary">{t("gift.subtitle")}</p>

          {view.subscription.prices.map((p) => {
            // As on S30/S31: `i18n-lint` needs a BARE identifier in the
            // template, so the plan is lifted out of the member expression.
            const plan = p.plan;
            return (
              <PriceCard
                key={p.plan}
                planLabel={t(`subscription.plan.${plan}`)}
                price={formatMoney(price(p))}
                periodLabel={t(
                  plan === "annual" ? "subscription.per_year" : "subscription.per_month",
                )}
                // §29.2's acceptance line, carried by a REQUIRED prop.
                totalWithTax={formatMoney(totalWithTax(p))}
                selected={selected === p.plan}
                onSelect={() => setSelected(p.plan)}
                foundingOffer={p.founding}
              />
            );
          })}

          {/* §30.3's honesty line, in the same words S30 uses. A prototype
              whose receipts are indistinguishable from real ones is one
              somebody eventually shows a customer. */}
          {view.subscription.simulated ? (
            <p className="text-caption text-ink-muted" data-testid="gift-simulated">
              {t("subscription.simulated")}
            </p>
          ) : null}

          <Button
            fullWidth
            loading={busy}
            data-testid="gift-buy"
            disabled={!view.subscription.purchasable}
            onClick={() => void onBuy()}
          >
            {t("gift.buy")}
          </Button>
        </div>
      ) : null}

      {view.kind === "bought" ? (
        <div className="flex flex-col gap-4" data-testid="gift-code">
          <Card as="section" className="flex flex-col gap-3">
            <h2 className="font-serif text-h2 text-ink-primary">{t("gift.code_title")}</h2>
            <p
              className="select-all font-mono text-h2 tracking-wide text-ink-primary"
              data-testid="gift-code-value"
            >
              {view.gift.code}
            </p>
            <p className="text-caption text-ink-muted">{t("gift.code_help")}</p>
            <Button
              variant="secondary"
              data-testid="gift-copy"
              onClick={() => {
                void navigator.clipboard?.writeText(view.gift.code).then(
                  () => setCopied(true),
                  // A clipboard the browser refused is not an error worth a
                  // screen — the code is selectable and visible right above.
                  () => setCopied(false),
                );
              }}
            >
              {t(copied ? "gift.copied" : "gift.copy")}
            </Button>
          </Card>

          <p className="text-caption text-ink-muted">
            {t("gift.expires", {
              date: new Date(view.gift.expires_at).toLocaleDateString(undefined, {
                day: "numeric",
                month: "long",
                year: "numeric",
              }),
            })}
          </p>
          <p className="text-caption text-ink-muted">{t("gift.recipient_note")}</p>

          {view.gift.simulated ? (
            <p className="text-caption text-ink-muted">{t("subscription.simulated")}</p>
          ) : null}
        </div>
      ) : null}
    </YouShell>
  );
}
