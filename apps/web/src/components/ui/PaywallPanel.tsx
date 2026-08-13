"use client";

/**
 * PaywallPanel — §24.3 feedback / §0.9 invitation register / S31.
 *
 * The §29.2 dark-pattern checklist is the component's API contract:
 *   · no countdown          — there is no timer prop and no place to put one
 *   · no guilt copy         — the Tara line is a fixed invitation key
 *   · close always visible  — the Sheet's close control is always rendered
 *   · price incl. tax shown before the rail — PriceCard requires totalWithTax
 *
 * The value recap is personalised from HER data (her chart, her memories count),
 * which is the honest reason to continue — not manufactured urgency.
 */

import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { Button } from "./Button";
import { Sheet } from "./Sheet";
import { TaraPresence } from "./TaraPresence";
import { cn, focusRing } from "./_util";

export interface PaywallPanelProps {
  open: boolean;
  onClose: () => void;
  /** Personalised recap lines, already localised (e.g. "42 memories kept"). */
  valueRecap: string[];
  /** PriceCard elements. */
  children: ReactNode;
  onContinue: () => void;
  onRestorePurchase?: () => void;
  onOpenGift?: () => void;
  busy?: boolean;
  className?: string;
}

export function PaywallPanel({
  open,
  onClose,
  valueRecap,
  children,
  onContinue,
  onRestorePurchase,
  onOpenGift,
  busy = false,
  className,
}: PaywallPanelProps) {
  const t = useTranslations();

  return (
    <Sheet
      open={open}
      onClose={onClose}
      titleKey="ui.paywall.title"
      className={className}
      footer={
        <div className="flex flex-col gap-2">
          <Button fullWidth loading={busy} onClick={onContinue}>
            {t("ui.paywall.continue")}
          </Button>
          <div className="flex flex-wrap items-center justify-center gap-4">
            {onOpenGift ? (
              <button
                type="button"
                onClick={onOpenGift}
                className={cn(
                  "rounded-chip px-2 py-1 text-caption text-ink-primary underline decoration-gold underline-offset-4",
                  focusRing,
                )}
              >
                {t("ui.paywall.gift")}
              </button>
            ) : null}
            {onRestorePurchase ? (
              <button
                type="button"
                onClick={onRestorePurchase}
                className={cn(
                  "rounded-chip px-2 py-1 text-caption text-ink-primary underline decoration-gold underline-offset-4",
                  focusRing,
                )}
              >
                {t("ui.paywall.restore")}
              </button>
            ) : null}
          </div>
        </div>
      }
    >
      <div className="flex flex-col gap-4">
        <div className="flex items-center gap-3">
          {/* state 1, small — never pleading imagery (§29.5) */}
          <TaraPresence size="sm" state="welcome" still />
          <p className="max-w-reading font-serif text-h3 text-ink-primary">
            {t("ui.paywall.tara_line")}
          </p>
        </div>

        <ul className="flex flex-col gap-2">
          {valueRecap.map((line) => (
            <li key={line} className="text-body text-ink-muted">
              {line}
            </li>
          ))}
        </ul>

        <div role="radiogroup" aria-label={t("ui.paywall.plans")} className="flex flex-col gap-2">
          {children}
        </div>
      </div>
    </Sheet>
  );
}
