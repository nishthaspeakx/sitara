"use client";

/**
 * ReceiptRow — §24.3 feedback / §30.3. One transaction on S30.
 *
 * §30.3 fixes the payment states this has to be able to say honestly:
 * success · pending (UPI waiting) · failed (plain-language reason) · refunded.
 * A pending UPI mandate is not an error, so it does not borrow the error colour;
 * a failure states the mapped reason rather than a code.
 */

import { useTranslations } from "next-intl";

import { cn, focusRing, motionStandard } from "./_util";

export type ReceiptStatus = "paid" | "pending" | "failed" | "refunded";

export interface ReceiptRowProps {
  /** Plan/description, already localised. */
  description: string;
  /** Formatted in the transaction's own currency (§30.3 — never converted). */
  amount: string;
  /** Formatted in-locale. */
  date: string;
  status: ReceiptStatus;
  /** Plain-language reason for `failed`, already localised. */
  reason?: string;
  onOpenInvoice?: () => void;
  className?: string;
}

const STATUS_TEXT: Record<ReceiptStatus, string> = {
  paid: "text-feedback-success-text",
  pending: "text-ink-muted",
  failed: "text-feedback-danger-text",
  refunded: "text-ink-muted",
};

const STATUS_GLYPH: Record<ReceiptStatus, string> = {
  paid: "✓",
  pending: "…",
  failed: "⚠",
  refunded: "↩",
};

export function ReceiptRow({
  description,
  amount,
  date,
  status,
  reason,
  onOpenInvoice,
  className,
}: ReceiptRowProps) {
  const t = useTranslations();
  return (
    <div
      className={cn(
        "flex flex-col gap-1 border-b border-border-subtle py-3",
        className,
      )}
    >
      <div className="flex items-baseline justify-between gap-3">
        <span className="min-w-0 truncate text-body text-ink-primary">{description}</span>
        <span className="shrink-0 text-body text-ink-primary tabular-nums">{amount}</span>
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="text-caption text-ink-muted tabular-nums">{date}</span>
        <span className={cn("flex items-center gap-1 text-caption", STATUS_TEXT[status])}>
          {/* glyph as well as colour — §29.4 never encodes state by colour alone */}
          <span aria-hidden="true">{STATUS_GLYPH[status]}</span>
          {t(`ui.receipt.${status}`)}
        </span>
        {onOpenInvoice ? (
          <button
            type="button"
            onClick={onOpenInvoice}
            className={cn(
              "rounded-chip px-2 py-1 text-caption text-ink-primary underline decoration-gold underline-offset-4",
              motionStandard,
              focusRing,
            )}
          >
            {t("ui.receipt.invoice")}
          </button>
        ) : null}
      </div>
      {status === "failed" && reason ? (
        <p className="text-caption text-ink-muted">{reason}</p>
      ) : null}
    </div>
  );
}
