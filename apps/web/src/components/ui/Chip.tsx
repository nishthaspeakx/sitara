"use client";

/**
 * Chip — §24.3 foundation. Variants: choice · filter · memory-consent.
 *
 * The memory-consent variant is the interaction §32.4 requires: a memory is
 * only ever offered, never taken. It is styled apart from choice/filter so a
 * consent decision can't be mistaken for a filter tap.
 */

import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { cn, focusRing, motionStandard, touchTarget, type MessageKey } from "./_util";

export type ChipVariant = "choice" | "filter" | "memory-consent";

export interface ChipProps {
  variant?: ChipVariant;
  selected?: boolean;
  disabled?: boolean;
  onClick?: () => void;
  /** Leading glyph; inherits currentColor. */
  icon?: ReactNode;
  /** Count badge for the filter variant. */
  count?: number;
  children: ReactNode;
  /** Accessible name override when the visible label is not enough. */
  labelKey?: MessageKey;
  className?: string;
}

export function Chip({
  variant = "choice",
  selected = false,
  disabled = false,
  onClick,
  icon,
  count,
  children,
  labelKey,
  className,
}: ChipProps) {
  const t = useTranslations();
  const base =
    variant === "memory-consent"
      ? cn(
          "border-dashed",
          selected
            ? "bg-gold-soft text-on-gold border-border-strong"
            : "bg-transparent text-ink-primary border-border-strong",
        )
      : selected
        ? "bg-gold-soft text-on-gold border-border-strong"
        : "bg-surface text-ink-primary border-border-subtle hover:bg-surface-sunken";

  return (
    <button
      type="button"
      role={variant === "filter" ? "switch" : undefined}
      aria-checked={variant === "filter" ? selected : undefined}
      aria-pressed={variant === "filter" ? undefined : selected}
      aria-label={labelKey ? t(labelKey) : undefined}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-2 rounded-chip border px-3 py-2 text-caption",
        touchTarget,
        motionStandard,
        focusRing,
        base,
        disabled && "cursor-not-allowed text-ink-muted border-border-subtle",
        className,
      )}
    >
      {icon ? <span aria-hidden="true">{icon}</span> : null}
      <span>{children}</span>
      {typeof count === "number" ? (
        <span className="rounded-chip bg-surface-sunken px-2 text-caption text-ink-muted">
          {count}
        </span>
      ) : null}
    </button>
  );
}
