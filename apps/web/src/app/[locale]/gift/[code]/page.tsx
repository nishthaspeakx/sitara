"use client";

/**
 * S33 — gift redeem (§29.1 `/gift/[code]`, §30.3).
 *
 * ── Why the code is in the URL ─────────────────────────────────────────────
 *
 * §29.1 routes this screen as `/gift/[code]` so a shared link opens prefilled.
 * The field stays editable and stays visible: someone who was read the code
 * down a phone line arrives at `/gift/-` and types it, and someone whose link
 * was mangled can fix it without hunting for a second entry point.
 *
 * ── Three outcomes, and the refusals are deliberately indistinguishable ────
 *
 * §30.3: "valid → onboarding with gift banner; already-subscribed → credit
 * conversion; expired/used → warm error + support link". The server answers
 * expired, used and unknown with ONE message key — a response that told them
 * apart would be an oracle for enumerating bearer instruments — so this screen
 * renders whatever `message_key` it is handed rather than branching on the
 * outcome. The outcome is carried for the log, not for the copy.
 *
 * ── The conversion case shows the giver's money, not hers ──────────────────
 *
 * §30.3: "gift credits are denominated in their purchase currency". A USD gift
 * redeemed by a ₹ subscriber extends her period and reports the giver's USD.
 * Rendering that amount as rupees would be exactly the conversion §30.3
 * forbids in four separate sentences, so `formatMoney` is handed the gift's
 * own currency and never hers.
 */

import { useTranslations } from "next-intl";
import { use, useEffect, useState } from "react";

import type { ErrorEnvelope } from "@sitara/schemas";

import { Button, Card, ErrorState, Input, TaraPresence } from "@/components/ui";
import { useRouter } from "@/i18n/navigation";
import { formatMoney } from "@/lib/money";
import { redeemGift, type RedemptionResult } from "@/lib/subscription";

type View =
  | { kind: "entry" }
  | { kind: "busy" }
  | { kind: "done"; result: RedemptionResult }
  | { kind: "refused"; error: ErrorEnvelope };

/** The placeholder route a link-less arrival uses. Never a real code. */
const BLANK = "-";

export default function GiftRedeemPage({
  params,
}: {
  params: Promise<{ code: string }>;
}) {
  const t = useTranslations();
  const router = useRouter();
  const { code: fromUrl } = use(params);

  const [code, setCode] = useState("");
  const [view, setView] = useState<View>({ kind: "entry" });

  useEffect(() => {
    const decoded = decodeURIComponent(fromUrl ?? "");
    if (decoded && decoded !== BLANK) setCode(decoded.toUpperCase());
  }, [fromUrl]);

  async function submit() {
    const trimmed = code.trim().toUpperCase();
    if (!trimmed) return;
    setView({ kind: "busy" });
    const result = await redeemGift(trimmed);
    setView(
      result.ok
        ? { kind: "done", result: result.data }
        : { kind: "refused", error: result.error },
    );
  }

  return (
    <main
      data-testid="gift-redeem"
      className="mx-auto flex min-h-app max-w-md flex-col gap-6 px-6 py-10"
    >
      <div className="flex justify-center">
        <TaraPresence size="lg" state="welcome" still showAiLabel />
      </div>

      <div className="flex flex-col gap-2 text-center">
        <h1 className="font-serif text-h1 text-ink-primary">{t("gift.redeem.title")}</h1>
        {view.kind !== "done" ? (
          <p className="text-body text-ink-secondary">{t("gift.redeem.subtitle")}</p>
        ) : null}
      </div>

      {view.kind === "done" ? (
        <Card as="section" className="flex flex-col gap-3" data-testid="gift-redeemed">
          {/* Whatever the server said, in her language. Not a sentence chosen
              here from the outcome — see the header. */}
          <p className="text-body text-ink-primary">{t(view.result.message_key)}</p>

          {view.result.gift_value ? (
            <p className="text-caption text-ink-muted" data-testid="gift-value">
              {t("gift.redeem.value", {
                amount: formatMoney(view.result.gift_value),
              })}
            </p>
          ) : null}

          {view.result.extended_to ? (
            <p className="text-caption text-ink-muted" data-testid="gift-extended">
              {t("gift.redeem.extended", {
                date: new Date(view.result.extended_to).toLocaleDateString(undefined, {
                  day: "numeric",
                  month: "long",
                  year: "numeric",
                }),
              })}
            </p>
          ) : null}

          <Button fullWidth data-testid="gift-open" onClick={() => router.push("/today")}>
            {t("gift.redeem.open")}
          </Button>
        </Card>
      ) : (
        <div className="flex flex-col gap-4">
          <Input
            labelKey="gift.redeem.label"
            placeholder={t("gift.redeem.placeholder")}
            value={code}
            autoCapitalize="characters"
            spellCheck={false}
            onChange={(event) => setCode(event.target.value)}
            data-testid="gift-code-input"
          />
          <Button
            fullWidth
            loading={view.kind === "busy"}
            disabled={!code.trim()}
            data-testid="gift-redeem-submit"
            onClick={() => void submit()}
          >
            {t("gift.redeem.cta")}
          </Button>

          {/* §30.3's "warm error + support link". `ErrorState` renders the
              §34.4 envelope's own message_key, which is the ONE key the server
              gives expired, used and unknown alike. */}
          {view.kind === "refused" ? (
            <ErrorState
              error={view.error}
              onRetry={() => setView({ kind: "entry" })}
            />
          ) : null}
        </div>
      )}
    </main>
  );
}
