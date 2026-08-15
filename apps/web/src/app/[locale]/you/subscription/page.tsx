"use client";

/**
 * S30 Subscription — §29.1 `/you/subscription`, §30.3 and §22.13.
 *
 * ── The screen's job is to say what is true, calmly ────────────────────────
 *
 * §22.13's ladder is the whole design brief and its posture is unusual: a
 * customer whose payment failed is not being chased. So the grace state leads
 * with what has NOT changed ("nothing has changed — you have everything until
 * {date}"), the read-only state leads with "your memories are safe", and the
 * downgraded state says nothing was deleted. §29.2 forbids countdowns and
 * guilt copy; §22.13 supplies the words that replace them.
 *
 * The dates are the load-bearing part. "One tap fixes it" is only reassuring
 * beside a real deadline, and §22.13's are 7 days and then 21 — so
 * `grace_ends_at` and `downgrades_at` come from the server, where the ladder
 * is computed, rather than being derived here from a failure timestamp. A
 * client that did that arithmetic would be a second implementation of §22.13,
 * and the two would disagree on exactly the day it mattered.
 *
 * ── Everything here is a §24.3 component, and one of them is a Card ────────
 *
 * No new components: §24.3 is fixed at 49 (CC-007). `ReceiptRow` and
 * `PriceCard` were built in M7 against §30.3's own state list, which is why
 * they already say `pending` without borrowing the error colour.
 *
 * **The never-subscribed state is a `Card`, not an `EmptyState`**, and that is
 * a deliberate refusal rather than an oversight. §24.6 fixes the empty states
 * at NINE and `EMPTY_STATES` is a closed list; "you have no subscription" is
 * not among them, and adding a tenth needs the §24.3 design-system review this
 * milestone has not had. `receipts` IS one of the nine and is used as one.
 *
 * ── Money formats on the client, and grouping follows the CURRENCY ─────────
 *
 * `lib/money.ts` carries the reasoning. The short version: the server sends
 * minor units, §2.3 gives INR Indian grouping and USD Western grouping, and
 * `Intl` groups by locale — so a `hi` reader looking at a USD price (an NRI
 * gift, a subscriber who moved) would otherwise see `$14,50,000`.
 */

import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import type { BillingRegion, ErrorEnvelope } from "@sitara/schemas";

import { YouShell } from "@/components/you/YouShell";
import {
  Button,
  Card,
  Chip,
  EmptyState,
  ErrorState,
  ListRow,
  SectionHeader,
  Sheet,
  Skeleton,
} from "@/components/ui";
import { useRouter } from "@/i18n/navigation";
import { formatLongDate } from "@/lib/dates";
import { formatMoney } from "@/lib/money";
import {
  cancelSubscription,
  loadSubscription,
  newIdempotencyKey,
  retryRenewal,
  subscriptionPrice,
  switchRegion,
  type Subscription,
} from "@/lib/subscription";

type View =
  | { kind: "loading" }
  | { kind: "ready"; subscription: Subscription }
  | { kind: "error"; error: ErrorEnvelope };

/** An ISO timestamp as a date the screen can print (CC-013: Latin numerals). */
function day(iso: string | null, locale: string): string {
  if (!iso) return "";
  return formatLongDate(iso.slice(0, 10), locale);
}

/** Which sentence the period line makes, given where §22.13 has got to. */
function renewalLineKey(
  status: NonNullable<Subscription["status"]>,
): "subscription.access_until" | "subscription.renews_on" | "subscription.paid_until" {
  if (status === "cancelled") return "subscription.access_until";
  if (status === "grace" || status === "read_only" || status === "downgraded") {
    return "subscription.paid_until";
  }
  return "subscription.renews_on";
}

function otherRegion(region: BillingRegion): BillingRegion {
  return region === "india" ? "international" : "india";
}

export default function SubscriptionPage() {
  const t = useTranslations();
  const locale = useLocale();
  const router = useRouter();
  const [view, setView] = useState<View>({ kind: "loading" });
  const [confirmingCancel, setConfirmingCancel] = useState(false);
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

  const onRetry = useCallback(async () => {
    if (view.kind !== "ready" || !view.subscription.plan || !view.subscription.region) return;
    setBusy(true);
    // The key is minted once, for THIS tap (§6.3, §30.3). A key per HTTP
    // request would make a retried request a second charge.
    const result = await retryRenewal({
      plan: view.subscription.plan,
      region: view.subscription.region,
      idempotencyKey: newIdempotencyKey(),
    });
    setBusy(false);
    if (result.ok && result.data.checkout_url) {
      window.location.assign(result.data.checkout_url);
      return;
    }
    await refresh();
  }, [view, refresh]);

  const onCancel = useCallback(async () => {
    setBusy(true);
    await cancelSubscription();
    setBusy(false);
    setConfirmingCancel(false);
    await refresh();
  }, [refresh]);

  return (
    <YouShell
      testId="subscription"
      titleKey="subscription.title"
      subtitleKey="subscription.subtitle"
      onBack={() => router.push("/you")}
    >
      {view.kind === "loading" ? <Skeleton variant="list" /> : null}

      {view.kind === "error" ? (
        <ErrorState error={view.error} onRetry={() => void refresh()} />
      ) : null}

      {view.kind === "ready" ? (
        <SubscriptionBody
          subscription={view.subscription}
          locale={locale}
          busy={busy}
          onRetry={() => void onRetry()}
          onCancel={() => setConfirmingCancel(true)}
          onSwitchRegion={(region) => {
            setBusy(true);
            void switchRegion(region).then(async () => {
              setBusy(false);
              await refresh();
            });
          }}
          onSubscribe={() => router.push("/you/subscription/checkout")}
        />
      ) : null}

      {/* §30.3: "one screen, immediate confirm, access till period end stated,
          no retention labyrinth". One sheet, two controls, and the destructive
          one is not the primary — §45.3's family sheet settled that ordering
          for the whole app. There is no "are you sure?" second step, no offer
          designed to change her mind, and no required reason. */}
      {view.kind === "ready" ? (
        <div data-testid="subscription-cancel-sheet">
          <Sheet
            open={confirmingCancel}
            onClose={() => setConfirmingCancel(false)}
            titleKey="subscription.cancel_title"
            footer={
              <div className="flex flex-col gap-2">
                <Button variant="secondary" fullWidth onClick={() => setConfirmingCancel(false)}>
                  {t("subscription.cancel_keep")}
                </Button>
                <Button
                  variant="tertiary"
                  fullWidth
                  loading={busy}
                  onClick={() => void onCancel()}
                >
                  {t("subscription.cancel_confirm")}
                </Button>
              </div>
            }
          >
            <p className="max-w-reading text-body text-ink-muted">
              {t("subscription.cancel_body", {
                date: day(view.subscription.period_end, locale),
              })}
            </p>
          </Sheet>
        </div>
      ) : null}
    </YouShell>
  );
}

interface BodyProps {
  subscription: Subscription;
  locale: string;
  busy: boolean;
  onRetry: () => void;
  onCancel: () => void;
  onSwitchRegion: (region: BillingRegion) => void;
  onSubscribe: () => void;
}

function SubscriptionBody({
  subscription,
  locale,
  busy,
  onRetry,
  onCancel,
  onSwitchRegion,
  onSubscribe,
}: BodyProps) {
  const t = useTranslations();
  const price = subscriptionPrice(subscription);
  // BARE identifiers, because `i18n-lint` matches the literal template text
  // against `dynamic-keys.json` and cannot expand `${subscription.plan}` — the
  // same rule `ui.module.${module}` and `ui.memory.type.${type}` already
  // follow. An unexpandable template is a template the §2.4 gate cannot check.
  const plan = subscription.plan ?? "monthly";
  const status = subscription.status;

  // An account that never subscribed. NOT the same screen as a downgraded
  // one: §22.13 leaves a downgraded account with a history it is entitled to
  // be told is safe, and somebody who never bought has none to reassure her
  // about. See the file header for why this is a Card rather than a tenth
  // EmptyState.
  if (subscription.status === null) {
    return (
      <>
        {subscription.simulated ? <SimulatedNotice /> : null}
        <div data-testid="subscription-none">
          <Card measure>
            <h2 className="font-serif text-h2 text-ink-primary">
              {t("subscription.none_title")}
            </h2>
            <p className="mt-2 text-body text-ink-muted">{t("subscription.none_body")}</p>
            {subscription.purchasable ? (
              <Button className="mt-4" onClick={onSubscribe}>
                {t("ui.paywall.continue")}
              </Button>
            ) : (
              // §30.3's gap, said plainly rather than as a broken button. No
              // rail serves this region yet (`payments.live_rails`), so there
              // is NO CONTROL for a purchase that cannot complete —
              // `ErrorState`'s `retryable: false` rule, applied to an
              // affordance. A disabled button would still assert it is nearly
              // there.
              <p
                data-testid="subscription-unavailable"
                className="mt-4 text-caption text-ink-muted"
              >
                {t("subscription.unavailable")}
              </p>
            )}
          </Card>
        </div>
      </>
    );
  }

  return (
    <>
      {subscription.simulated ? <SimulatedNotice /> : null}

      <div data-testid="subscription-summary">
        <Card>
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="font-serif text-h2 text-ink-primary">
                {t(`subscription.plan.${plan}`)}
              </span>
              {price ? (
                <span className="text-h3 text-ink-primary tabular-nums">
                  {formatMoney(price)}
                </span>
              ) : null}
            </div>

            {/* The state as a chip — §29.4 never encodes state by colour alone,
                and this is the word rather than the hue. */}
            <span data-testid="subscription-status" className="w-fit">
              <Chip variant="filter">{t(`subscription.status.${status}`)}</Chip>
            </span>

            {/* The renewal line must not contradict the card below it. The
                first Hindi baseline showed "renews on 1 August 2027" directly
                above "this month's payment didn't go through" — both true of
                different periods, and together a sentence nobody can read.
                Once a renewal has FAILED, `period_end` is the end of what she
                already paid for, so the honest line says that instead, and the
                §22.13 dates live on the dunning card where they belong. */}
            <p className="text-caption text-ink-muted tabular-nums">
              {t(renewalLineKey(subscription.status), {
                date: day(subscription.period_end, locale),
              })}
            </p>

            {subscription.founding ? (
              <p className="text-caption text-ink-muted">{t("subscription.founding_note")}</p>
            ) : null}
          </div>
        </Card>
      </div>

      {/* §22.13's two dunning states. Each leads with what has NOT changed. */}
      {subscription.status === "grace" ? (
        <div data-testid="subscription-grace">
          <Card tone="sunken" measure>
            <p className="text-body text-ink-primary">
              {t("subscription.grace_body", { date: day(subscription.grace_ends_at, locale) })}
            </p>
            <Button className="mt-3" loading={busy} onClick={onRetry}>
              {t("subscription.retry")}
            </Button>
          </Card>
        </div>
      ) : null}

      {subscription.status === "read_only" ? (
        <div data-testid="subscription-read-only">
          <Card tone="sunken" measure>
            <p className="text-body text-ink-primary">{t("subscription.read_only_body")}</p>
            <Button className="mt-3" loading={busy} onClick={onRetry}>
              {t("subscription.retry")}
            </Button>
          </Card>
        </div>
      ) : null}

      {subscription.status === "downgraded" || subscription.status === "expired" ? (
        <div data-testid="subscription-downgraded">
          <Card measure>
            <p className="text-body text-ink-primary">{t("subscription.downgraded_body")}</p>
          </Card>
        </div>
      ) : null}

      {/* §30.3 — "mandate rejected post-purchase (subscription active on paid
          period; mandate retry flow queued)". A note, never a status: the
          money arrived and only the next standing instruction did not. */}
      {subscription.mandate_retry_required ? (
        <div data-testid="subscription-mandate">
          <Card measure>
            <p className="text-body text-ink-primary">{t("subscription.mandate_body")}</p>
          </Card>
        </div>
      ) : null}

      {/* §30.3's billing-region migration — offered AT renewal, never before.
          `region_switch_offered` is the SERVER's answer to "is it renewal
          time"; asking the same question here would be §30.3's rule
          implemented twice, and the two would disagree on the renewal day. */}
      {subscription.region_switch_offered && subscription.region ? (
        <div data-testid="subscription-region">
          <Card measure>
            <SectionHeader level={2} titleKey="subscription.region_switch_title" />
            <p className="text-body text-ink-muted">
              {t("subscription.region_switch_body", {
                current: subscription.region,
                other: otherRegion(subscription.region),
                price: formatMoney(
                  (() => {
                    const match = subscription.prices.find((p) => p.plan === subscription.plan);
                    return {
                      minor: match?.amount_minor ?? 0,
                      currency: match?.currency ?? "INR",
                    };
                  })(),
                ),
              })}
            </p>
            <Button
              className="mt-3"
              variant="secondary"
              loading={busy}
              onClick={() => onSwitchRegion(otherRegion(subscription.region!))}
            >
              {t("subscription.region_switch", { other: otherRegion(subscription.region) })}
            </Button>
          </Card>
        </div>
      ) : null}

      {/* §30.3's cancellation entry. A plain row, at the bottom, with no
          friction in front of it and nothing designed to deflect. */}
      {subscription.status === "active" || subscription.status === "trialing" ? (
        <ul className="flex flex-col" data-testid="subscription-cancel">
          <li>
            <ListRow labelKey="subscription.cancel" onClick={onCancel} />
          </li>
        </ul>
      ) : null}

      <SectionHeader level={2} titleKey="subscription.receipts" />
      {/* `receipts` IS one of §24.6's nine designed empty states, and its own
          action is "See plans" — no dead ends. */}
      <div data-testid="subscription-receipts">
        <EmptyState id="receipts" onAction={onSubscribe} />
      </div>
    </>
  );
}

/**
 * The prototype's own disclosure.
 *
 * `routing.is_simulated` reaches the client as one boolean, and this is why it
 * does: a prototype whose receipts and states are indistinguishable from real
 * ones is a prototype somebody eventually shows to a customer. Same instinct
 * as CC-008's permanent "Tara · AI guide" disclosure — where a thing is not
 * what it appears to be, the screen says so.
 */
function SimulatedNotice() {
  const t = useTranslations();
  return (
    <p data-testid="subscription-simulated" className="text-caption text-ink-muted">
      {t("subscription.simulated")}
    </p>
  );
}
