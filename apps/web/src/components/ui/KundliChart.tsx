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
 * ── The diagram, drawn (M10) ────────────────────────────────────────────────
 * M7 shipped this file as a prop contract plus an honest unbuilt state so the
 * §24.3 count was true at 49 rather than counting something that did not
 * exist. M10 replaces the render and NOT the interface — CC-007 §40.2 promised
 * exactly that, and every prop below is the one M7 declared.
 *
 * What the two layouts are, and why both:
 * · **North Indian** — the HOUSES are fixed on the page and the rashis move.
 *   House 1 is always the top-centre diamond.
 * · **South Indian** — the RASHIS are fixed and the houses move. Mesha is
 *   always the same cell; the lagna is marked wherever it lands.
 *   CC-007: "neither is a fallback for the other". A reader of one cannot read
 *   the other by squinting, which is why the switch exists — and why
 *   `kundli-geometry.ts` places by a different key for each.
 *
 * What binds the render:
 * · §5.3 / §9 — the LLM never computes a chart. Every placement arrives as an
 *   engine fact, resolved by the caller. No ephemeris, no house maths, no
 *   ayanamsa here; `houses` is data in, diagram out.
 * · §5.4 — the confidence renders ON the artefact, not beside it: a diamond
 *   drawn with a guessed ascendant is a confident-looking lie. Moon-chart mode
 *   is labelled as chandra lagna rather than quietly drawn as an ordinary
 *   chart with the lagna marker missing.
 * · §24.2 — token-only styling, both themes. Houses that carry nothing stay
 *   empty rather than being filled with decoration.
 * · §24.2 / §2.3 — graha labels are script-aware: a Hindi user reads सू where
 *   an English user reads Su, at the line-height the active script needs. The
 *   glyphs inside the boxes are ABBREVIATIONS, as on paper — a chart wide
 *   enough to spell "Mercury" in nine boxes is not a kundli, it is a table —
 *   and the full names are in the list below the diagram, which is also what
 *   a screen reader and a small viewport get.
 * · §29.4 — no state is carried by colour alone. The lagna has a label in the
 *   north chart and a corner rule in the south, both of which survive being
 *   printed in grey.
 */

import { useTranslations } from "next-intl";

import { Card } from "./Card";
import { ConfidenceChip } from "./ConfidenceChip";
import { SegmentedControl } from "./SegmentedControl";
import { cn, type ConfidenceState } from "./_util";
import {
  NORTH_HOUSES,
  NORTH_LINES,
  SOUTH_CELLS,
  SOUTH_LINES,
  VIEWBOX,
  southLagnaMark,
  type Cell,
} from "./kundli-geometry";

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
   * §5.4 — `approximate` where the birth time is a window, `tradition_based_general`
   * in Moon-chart mode. A chart drawn from a guessed lagna must say so.
   */
  confidence?: ConfidenceState;
  /** Opens the TrustSheet for the chart as a whole (§30.4, ≤1 tap). */
  onWhyThis?: () => void;
  className?: string;
}

/** Two per line keeps a stellium inside its box in the narrowest triangle. */
function chunk<T>(items: readonly T[], size: number): T[][] {
  const rows: T[][] = [];
  for (let i = 0; i < items.length; i += size) rows.push(items.slice(i, i + size));
  return rows;
}

export function KundliChart({
  houses,
  style = "north",
  onStyleChange,
  confidence,
  className,
}: KundliChartProps) {
  const t = useTranslations();

  /*
    The two traditions place by a DIFFERENT key, and that is the whole
    difference between them: north indexes by house (house 1 is always the top
    diamond), south indexes by rashi (Mesha is always the same cell). Getting
    this wrong produces a chart that looks like a kundli and reads as gibberish
    to anyone who grew up with the other one.

    A house whose rashi is outside 1–12 is skipped rather than clamped: the
    caller resolved it from engine facts, so an impossible value means the
    resolution is wrong, and drawing it in Mesha would hide that.
  */
  const cells = houses
    .map((house) => ({
      house,
      cell:
        style === "north"
          ? NORTH_HOUSES[house.house - 1]
          : SOUTH_CELLS[house.rashi - 1],
    }))
    .filter((entry): entry is { house: KundliHouse; cell: Cell } => Boolean(entry.cell));

  const lagnaCell = cells.find(({ house }) => house.isLagna)?.cell;
  const southLagnaPath = lagnaCell ? southLagnaMark(lagnaCell) : null;

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

      <svg
        viewBox={VIEWBOX}
        role="img"
        aria-label={t(
          style === "north" ? "ui.kundli.diagram_north" : "ui.kundli.diagram_south",
        )}
        className="aspect-square w-full text-ink-primary"
      >
        {/*
          The rules first, so the glyphs sit on top of them. `stroke-current`
          takes the ink colour from the parent, which is how both themes are
          served without this file naming a colour.
        */}
        {(style === "north" ? NORTH_LINES : SOUTH_LINES).map((d) => (
          <path
            key={d}
            d={d}
            className="fill-none stroke-border-strong"
            strokeWidth={0.6}
            vectorEffect="non-scaling-stroke"
          />
        ))}

        {style === "south" && southLagnaPath ? (
          <path
            d={southLagnaPath}
            className="fill-none stroke-border-strong"
            strokeWidth={0.6}
            vectorEffect="non-scaling-stroke"
          />
        ) : null}

        {cells.map(({ cell, house }) => (
          <g key={house.house}>
            {/*
              The rashi number, small and in the corner, exactly where it sits
              on paper. It is a NUMBER rather than a name because the boxes are
              small and the numeral is the same in every script the launch
              locales use.
            */}
            <text
              x={cell.labelX}
              y={cell.labelY}
              textAnchor="middle"
              className="fill-ink-muted"
              fontSize={5}
            >
              {house.rashi}
            </text>
            {/*
              Two glyphs per line, as on paper. A single line overflowed the
              box the moment a house held three grahas — which is not an edge
              case but a stellium, the most interesting thing a chart can show,
              and it ran straight off the right edge of the diagram in both
              traditions. Caught by the first baseline; no typecheck or lint
              could have seen it.
            */}
            {chunk(house.grahas, 2).map((row, index) => (
              <text
                key={row.join("-")}
                x={cell.labelX}
                y={cell.labelY + 8 + index * 6}
                textAnchor="middle"
                className="fill-ink-primary"
                fontSize={5}
              >
                {row.map((g) => t(`ui.kundli.graha_short.${g}`)).join(" ")}
              </text>
            ))}
            {house.isLagna && style === "north" ? (
              <text
                x={cell.labelX}
                y={cell.labelY + 9 + chunk(house.grahas, 2).length * 6}
                textAnchor="middle"
                className="fill-ink-muted"
                fontSize={4}
              >
                {t("ui.kundli.lagna")}
              </text>
            ) : null}
          </g>
        ))}
      </svg>

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
