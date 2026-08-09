"use client";

/**
 * PanchangStrip — §24.3 Sitara-specific. The tithi · nakshatra · timings ribbon
 * on Today (S14), script-aware.
 *
 * §29.4 dataviz rules: numerals per locale, tabular-lining figures, label column
 * legible at 320px where the strip wraps to a 2×2 grid (§29.3).
 *
 * Every value arrives already rendered from an engine fact — the LLM never
 * computes panchang (§5.3), and this component never formats a date itself.
 */

import { useTranslations } from "next-intl";

import { cn } from "./_util";

export interface PanchangEntry {
  /** i18n key for the label: ui.panchang.tithi, .nakshatra, .yoga, .karana, .vaara */
  labelKey: string;
  /** The value, already localised (term from the glossary, numerals per locale). */
  value: string;
}

export interface PanchangStripProps {
  entries: PanchangEntry[];
  /** Shown when the almanac could not be resolved — the strip states it plainly. */
  unavailable?: boolean;
  className?: string;
}

export function PanchangStrip({ entries, unavailable = false, className }: PanchangStripProps) {
  const t = useTranslations();

  if (unavailable) {
    return (
      <p
        className={cn(
          "rounded-card border border-border-subtle bg-surface-sunken p-3 text-caption text-ink-muted",
          className,
        )}
      >
        {t("ui.panchang.unavailable")}
      </p>
    );
  }

  return (
    <dl
      aria-label={t("ui.panchang.label")}
      className={cn(
        // 320px wraps to a 2×2 grid; the design target lays it out in a row (§29.3)
        "grid grid-cols-2 gap-3 rounded-card border border-border-subtle bg-surface p-3",
        "phone:flex phone:flex-wrap phone:items-center",
        className,
      )}
    >
      {entries.map((entry) => (
        <div key={entry.labelKey} className="flex min-w-0 flex-col phone:flex-1">
          <dt className="text-caption text-ink-muted">{t(entry.labelKey)}</dt>
          <dd className="truncate text-body text-ink-primary tabular-nums">{entry.value}</dd>
        </div>
      ))}
    </dl>
  );
}
