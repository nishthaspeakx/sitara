"use client";

/**
 * KundliChart — §24.3 Sitara-specific (added by CC-007, taking the library to 49).
 *
 * The traditional birth-chart diagram: **North Indian diamond by default,
 * South Indian square as a user-switchable variant.** The visual kundli is a
 * core cultural artefact for an astrology-first Indian product — a user who has
 * seen her chart on paper her whole life expects to see it here, and a list of
 * house positions is not the same object.
 *
 * ── STATUS: CONTRACT ONLY, RENDERING LANDS IN M10 ───────────────────────────
 * CC-007 scheduled the diagram for M10, alongside Journal/Vault/Family. This
 * file is deliberately the full prop contract plus an honest unbuilt state, so
 * the §24.3 count test is TRUE at 49 rather than counting a component that does
 * not exist. It renders a labelled placeholder, never a wrong chart.
 *
 * ── What M10 must honour ────────────────────────────────────────────────────
 * · §5.3 / §9 — the LLM never computes a chart. Every graha placement arrives
 *   as an engine fact from the M2 chart tools, already resolved by the caller.
 *   This component has no ephemeris, no house maths and no ayanamsa; it is a
 *   renderer. `houses` is data in, diagram out.
 * · §5.4 — an unknown birth time means Moon-chart mode and lagna-sensitive
 *   claims are suppressed. The chart therefore takes a `confidence` and shows
 *   it: a diamond drawn with a guessed ascendant is a confident-looking lie.
 * · §24.2 — token-only styling, both themes. The grid is border-strong, the
 *   graha glyphs are ink, houses that carry nothing stay empty rather than
 *   being filled with decoration.
 * · §24.2 / §2.3 — graha labels are script-aware: they render through the
 *   catalogs, so a Hindi user sees सूर्य where an English user sees Sun, at the
 *   line-height the active script needs.
 * · §29.4 — never encode a house's quality by colour alone.
 */

import { useTranslations } from "next-intl";

import { Card } from "./Card";
import { ConfidenceChip } from "./ConfidenceChip";
import { SegmentedControl } from "./SegmentedControl";
import { cn, type ConfidenceState } from "./_util";

/** The two diagram traditions §24.3 requires, user-switchable. */
export const KUNDLI_STYLES = ["north", "south"] as const;
export type KundliStyle = (typeof KUNDLI_STYLES)[number];

/**
 * The nine grahas. Rahu and Ketu are chhaya grahas and are included — a kundli
 * without them is not a kundli.
 */
export const GRAHAS = [
  "sun",
  "moon",
  "mars",
  "mercury",
  "jupiter",
  "venus",
  "saturn",
  "rahu",
  "ketu",
] as const;
export type Graha = (typeof GRAHAS)[number];

export interface KundliHouse {
  /** 1–12, counted from the lagna for the north style and fixed for the south. */
  house: number;
  /** Rashi occupying the house, 1–12 (Mesha = 1). */
  rashi: number;
  /** Grahas placed in this house, from the engine's chart facts. */
  grahas: Graha[];
  /** True for the house holding the lagna. */
  isLagna?: boolean;
}

export interface KundliChartProps {
  /** Twelve entries, resolved from M2 chart facts by the caller — never computed here. */
  houses: KundliHouse[];
  /** North Indian diamond is the default (§24.3 / CC-007). */
  style?: KundliStyle;
  onStyleChange?: (style: KundliStyle) => void;
  /**
   * §5.4 — `approximate` where the birth time is a window, `tradition_general`
   * in Moon-chart mode. A chart drawn from a guessed lagna must say so.
   */
  confidence?: ConfidenceState;
  /** Opens the TrustSheet for the chart as a whole (§30.4, ≤1 tap). */
  onWhyThis?: () => void;
  className?: string;
}

export function KundliChart({
  houses,
  style = "north",
  onStyleChange,
  confidence,
  className,
}: KundliChartProps) {
  const t = useTranslations();

  return (
    <Card className={cn("flex flex-col gap-3", className)}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-serif text-h3 text-ink-primary">{t("ui.kundli.title")}</h3>
        {onStyleChange ? (
          <SegmentedControl
            labelKey="ui.kundli.style_label"
            segments={[
              { value: "north", labelKey: "ui.kundli.style.north" },
              { value: "south", labelKey: "ui.kundli.style.south" },
            ]}
            value={style}
            onChange={(next) => onStyleChange(next as KundliStyle)}
          />
        ) : null}
      </div>

      {/*
        The unbuilt state. It states plainly that the diagram is not drawn yet
        and shows the house data it WOULD draw, so the component is useful and
        honest in M8 without pretending to be finished. M10 replaces this block
        with the diagram; the props above do not change.
      */}
      <div
        role="img"
        aria-label={t("ui.kundli.pending_label")}
        className="flex aspect-square w-full items-center justify-center rounded-card border border-dashed border-border-strong bg-surface-sunken p-4"
      >
        <p className="max-w-reading text-center text-caption text-ink-muted">
          {t("ui.kundli.pending")}
        </p>
      </div>

      <ol className="flex flex-col gap-1">
        {houses.map((h) => (
          <li key={h.house} className="flex items-baseline gap-2 text-caption">
            <span className="w-16 shrink-0 text-ink-muted tabular-nums">
              {t("ui.kundli.house", { house: h.house })}
            </span>
            <span className="text-ink-primary">{t(`ui.kundli.rashi.${h.rashi}`)}</span>
            <span className="text-ink-muted">
              {h.grahas.map((g) => t(`ui.kundli.graha.${g}`)).join(" · ")}
            </span>
            {h.isLagna ? (
              <span className="rounded-chip border border-border-strong px-2 text-ink-primary">
                {t("ui.kundli.lagna")}
              </span>
            ) : null}
          </li>
        ))}
      </ol>

      {confidence ? <ConfidenceChip state={confidence} withDescription /> : null}
    </Card>
  );
}
