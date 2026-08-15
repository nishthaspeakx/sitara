"use client";

/**
 * S34 Payment result — §29.1's "one screen, three states" (§30.3).
 *
 * §29.1 names it exactly that way, and the three are not variations on a
 * theme:
 *
 *   **success** — the receipt is coming, and nothing needs doing.
 *   **pending** — §30.3's UPI hold. "Approve in your UPI app", up to five
 *                 minutes. **This is not an error**, and the screen does not
 *                 borrow an error's colour, glyph or tone for it. `ReceiptRow`
 *                 made the same choice in M7 before there was a payments
 *                 module behind it.
 *   **failed**  — §30.3's mapped reason "in plain language: insufficient funds
 *                 / mandate declined / bank timeout", one retry CTA, and an
 *                 alternate-rail suggestion.
 *
 * ── The reason is a KEY, and the mapping happened on the server ────────────
 *
 * §30.3 requires plain language; §2.4 forbids a silent English fallback; §13
 * keeps vendor payloads out of logs and screens. So the adapter maps a rail's
 * own failure code onto `PaymentFailureReason` before it ever leaves the
 * server, and this screen looks up `payresult.reason_<value>`. There is no
 * branch here that could render a vendor string, because no vendor string
 * reaches this far.
 *
 * `unknown` is a real member of that enum and gets a real line: "Your bank
 * didn't say why." A screen that guessed at a cause would be inventing a fact
 * about somebody's bank account, which is §5.3's rule pointed at money.
 *
 * ── Why this reads its state from the URL ─────────────────────────────────
 *
 * §30.3 sends the user to a hosted rail surface and gets her back on a
 * redirect. A redirect carries query parameters and nothing else — no
 * component state survives it — so the state has to be in the URL for the real
 * flow to work at all. The parameters are DISPLAY only: the entitlement comes
 * from `GET /v1/subscription`, which reads the database, so a hand-edited
 * `?state=success` shows an optimistic screen and grants exactly nothing.
 */

import { useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import { UPI_PENDING_HOLD_MINUTES } from "@sitara/schemas";

import { YouShell } from "@/components/you/YouShell";
import { Button, Card, Skeleton, TaraPresence } from "@/components/ui";
import { useRouter } from "@/i18n/navigation";
import { loadSubscription, type Subscription } from "@/lib/subscription";

const STATES = ["success", "pending", "failed"] as const;
type ResultState = (typeof STATES)[number];

/** §30.3's five mapped reasons. Unrecognised input falls to `unknown`, which
 *  is a real member with real copy rather than a blank. */
const REASONS = [
  "insufficient_funds",
  "mandate_declined",
  "bank_timeout",
  "instrument_expired",
  "unknown",
] as const;

function readState(raw: string | null): ResultState {
  return (STATES as readonly string[]).includes(raw ?? "") ? (raw as ResultState) : "failed";
}

function readReason(raw: string | null): (typeof REASONS)[number] {
  return (REASONS as readonly string[]).includes(raw ?? "")
    ? (raw as (typeof REASONS)[number])
    : "unknown";
}

export default function PaymentResultPage() {
  // `useSearchParams` needs a Suspense boundary in the App Router; without one
  // the whole route opts out of static rendering and Next warns at build.
  return (
    <Suspense fallback={<Skeleton variant="list" />}>
      <PaymentResult />
    </Suspense>
  );
}

function PaymentResult() {
  const t = useTranslations();
  const router = useRouter();
  const params = useSearchParams();
  const state = readState(params.get("state"));
  const reason = readReason(params.get("reason"));
  const [subscription, setSubscription] = useState<Subscription | null>(null);

  const refresh = useCallback(async () => {
    const result = await loadSubscription();
    if (result.ok) setSubscription(result.data);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    // §30.3's pending state is a POLL beside a webhook, and the two race
    // deliberately — whichever lands first wins, because `handle_event` is
    // idempotent (§6.4's unique index). A poll alone would strand a user whose
    // webhook arrived while her tab was closed; a webhook alone would leave
    // this screen spinning until she reloaded.
    if (state !== "pending") return;
    const timer = setInterval(() => void refresh(), 3000);
    return () => clearInterval(timer);
  }, [state, refresh]);

  const settled = subscription?.status === "active";

  return (
    <YouShell
      testId="payresult"
      titleKey={`payresult.title.${state}`}
      withTabs={false}
      onBack={() => router.push("/you/subscription")}
    >
      <div data-testid={`payresult-${state}`}>
        <Card measure>
          <div className="flex flex-col items-start gap-3">
            {/* §29.5 forbids Tara from being the face of a FAILED screen, so
                she appears on success and on the pending wait — which is not a
                failure — and not on the failure. */}
            {/* `showAiLabel` because CC-008's disclosure is permanent wherever
                her face appears, and this is a face on a screen about money.
                The first baseline showed the portrait with nothing beside it. */}
            {state !== "failed" ? (
              <TaraPresence size="sm" state="welcome" still showAiLabel />
            ) : null}

            <p className="text-body text-ink-primary">
              {state === "success" ? t("payresult.success_body") : null}
              {state === "pending" ? t("payresult.pending_body") : null}
              {state === "failed" ? t(`payresult.reason.${reason}`) : null}
            </p>

            {state === "pending" ? (
              <p className="text-caption text-ink-muted tabular-nums">
                {/* The five minutes come from the schema constant, not from a
                    literal here — the hold screen and the server's own
                    `UPI_PENDING_HOLD_MINUTES` must say the same number. */}
                {t("payresult.pending_hold", { minutes: UPI_PENDING_HOLD_MINUTES })}
              </p>
            ) : null}

            {/* §30.3's failure affordances: "one retry CTA + alternate-rail
                suggestion". One retry, not a row of them. */}
            {state === "failed" ? (
              <div className="flex flex-col gap-2 pt-1">
                <Button onClick={() => router.push("/you/subscription/checkout")}>
                  {t("payresult.try_again")}
                </Button>
                <Button
                  variant="tertiary"
                  onClick={() => router.push("/you/subscription/checkout")}
                >
                  {t("payresult.try_other")}
                </Button>
              </div>
            ) : null}

            {state === "success" || settled ? (
              <Button
                variant="secondary"
                onClick={() => router.push("/you/subscription")}
              >
                {t("payresult.back")}
              </Button>
            ) : null}
          </div>
        </Card>
      </div>
    </YouShell>
  );
}
