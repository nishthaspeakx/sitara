"use client";

/**
 * PriceCard — §24.3 feedback / §30.3.
 *
 * §29.2 + §30.3 acceptance, both enforced by the props: the **total including
 * tax is shown before the payment rail**, and savings are stated plainly. There
 * is no countdown prop, no "only today" prop, no strikethrough-anchor prop —
 * the component cannot express a dark pattern.
 *
 * Prices arrive pre-formatted in the user's billing currency (§30.3 keeps the
 * original currency until renewal), so this never does currency maths.
 */

import { Check } from "lucide-react";
import { useTranslations } from "next-intl";

import { ICON_STROKE, cn, focusRing, motionStandard } from "./_util";

export interface PriceCardProps {
  /** "Monthly" / "Annual", already localised. */
  planLabel: string;
  /** Headline price, formatted in the billing currency. */
  price: string;
  /** Billing period line, already localised. */
  periodLabel: string;
  /** Total incl. tax — REQUIRED before the rail (§30.3 acceptance). */
  totalWithTax: string;
  /** Plain savings statement, already localised. Omit when there is none. */
  savingsLabel?: string;
  selected?: boolean;
  onSelect?: () => void;
  /** Founding offer, where live. Descriptive only — never a timer. */
  foundingOffer?: boolean;
  className?: string;
}

export function PriceCard({
  planLabel,
  price,
  periodLabel,
  totalWithTax,
  savingsLabel,
  selected = false,
  onSelect,
  foundingOffer = false,
  className,
}: PriceCardProps) {
  const t = useTranslations();
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      onClick={onSelect}
      className={cn(
        "flex w-full flex-col gap-2 rounded-card border p-4 text-start",
        motionStandard,
        focusRing,
        selected
          ? "border-gold bg-surface shadow-card"
          : "border-border-subtle bg-surface hover:bg-surface-sunken",
        className,
      )}
    >
      <span className="flex items-center justify-between gap-2">
        <span className="font-serif text-h3 text-ink-primary">{planLabel}</span>
        {selected ? (
          <Check aria-hidden="true" strokeWidth={ICON_STROKE} className="shrink-0 text-ink-primary" />
        ) : null}
      </span>

      <span className="flex items-baseline gap-2">
        <span className="text-display text-ink-primary tabular-nums">{price}</span>
        <span className="text-caption text-ink-muted">{periodLabel}</span>
      </span>

      {/* the total including tax, before any rail handoff — §30.3 acceptance */}
      <span className="text-caption text-ink-muted tabular-nums">
        {t("ui.price.total_with_tax", { total: totalWithTax })}
      </span>

      {savingsLabel ? <span className="text-caption text-ink-primary">{savingsLabel}</span> : null}

      {foundingOffer ? (
        <span className="w-fit rounded-chip bg-gold-soft px-2 py-1 text-caption text-on-gold">
          {t("ui.price.founding_offer")}
        </span>
      ) : null}
    </button>
  );
}
