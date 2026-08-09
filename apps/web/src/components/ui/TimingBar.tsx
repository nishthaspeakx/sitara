"use client";

/**
 * TimingBar — §24.3 Sitara-specific. The choghadiya / rahu-kaal day
 * visualisation, colour-safe.
 *
 * §29.4, load-bearing: **auspicious and care are NEVER encoded by colour alone.**
 * Every band carries its glyph (⬆ favourable / ⚠ gentle care) and its label in
 * the legend, so the bar reads identically in greyscale and to a screen reader.
 * The care band uses `astro-care` — amber, never red (§24.2).
 *
 * A time-of-day x-axis with a now-marker, per the §29.4 dataviz rules. No pie
 * charts anywhere in this product.
 */

import { useTranslations } from "next-intl";

import { cn } from "./_util";

export type TimingQuality = "favourable" | "care" | "neutral";

export interface TimingBand {
  /** Name of the window, already localised (e.g. "Rahu Kaal", "Amrit"). */
  label: string;
  /** Start/end as minutes from midnight, local to the stated city (§30.2). */
  startMinute: number;
  endMinute: number;
  quality: TimingQuality;
  /** Formatted range for the tooltip/legend, e.g. "09:12 – 10:48". */
  range: string;
}

const QUALITY_FILL: Record<TimingQuality, string> = {
  favourable: "bg-astro-auspicious",
  care: "bg-astro-care",
  neutral: "bg-border-subtle",
};

const QUALITY_GLYPH: Record<TimingQuality, string> = {
  favourable: "⬆",
  care: "⚠",
  neutral: "·",
};

const DAY_MINUTES = 24 * 60;

export interface TimingBarProps {
  bands: TimingBand[];
  /** Minutes from midnight; renders the now-marker. Omit to hide it. */
  nowMinute?: number;
  /** The city the timings were computed for — never implied (§30.2). */
  placeLabel?: string;
  className?: string;
}

export function TimingBar({ bands, nowMinute, placeLabel, className }: TimingBarProps) {
  const t = useTranslations();
  const pct = (minute: number) => `${((minute / DAY_MINUTES) * 100).toFixed(3)}%`;

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      {placeLabel ? (
        <p className="text-caption text-ink-muted">{t("ui.timing.place", { place: placeLabel })}</p>
      ) : null}

      <div
        role="img"
        aria-label={t("ui.timing.chart_label")}
        className="relative h-8 w-full overflow-hidden rounded-chip bg-surface-sunken"
      >
        {bands.map((band) => (
          <span
            key={`${band.startMinute}-${band.label}`}
            className={cn(
              "absolute inset-y-0 flex items-center justify-center",
              QUALITY_FILL[band.quality],
            )}
            style={{
              insetInlineStart: pct(band.startMinute),
              width: pct(band.endMinute - band.startMinute),
            }}
          >
            {/* pattern redundancy — the glyph, not the fill, carries the meaning */}
            <span aria-hidden="true" className="text-caption text-on-gold">
              {QUALITY_GLYPH[band.quality]}
            </span>
          </span>
        ))}
        {typeof nowMinute === "number" ? (
          <span
            aria-hidden="true"
            style={{ insetInlineStart: pct(nowMinute) }}
            className="absolute inset-y-0 w-px bg-ink-primary"
          />
        ) : null}
      </div>

      {/* the legend IS the accessible reading of the chart */}
      <ul className="flex flex-col gap-1">
        {bands.map((band) => (
          <li
            key={`legend-${band.startMinute}-${band.label}`}
            className="flex items-center gap-2 text-caption"
          >
            <span aria-hidden="true" className={cn("h-3 w-3 rounded-chip", QUALITY_FILL[band.quality])} />
            <span aria-hidden="true">{QUALITY_GLYPH[band.quality]}</span>
            <span className="text-ink-primary">{band.label}</span>
            <span className="text-ink-muted tabular-nums">{band.range}</span>
            <span className="text-ink-muted">{t(`ui.timing.${band.quality}`)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
