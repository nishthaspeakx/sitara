/**
 * The two kundli layouts, as geometry (§24.3, CC-007).
 *
 * Separated from the component because they are DATA — twelve polygons and
 * twelve label anchors per tradition — and because the difference between the
 * two is the thing most likely to be got wrong by someone who has only seen
 * one of them:
 *
 * · **North Indian**: the HOUSES are fixed on the page and the rashis move.
 *   House 1 is always the top-centre diamond; which sign sits in it depends on
 *   the lagna.
 * · **South Indian**: the RASHIS are fixed on the page and the houses move.
 *   Mesha is always the same cell; the lagna is marked wherever it falls.
 *
 * CC-007: "neither is a fallback for the other". They are regional traditions,
 * and a reader of one cannot read the other by squinting — which is exactly
 * why the switch exists and why this file places by a different key for each.
 *
 * All coordinates are in a unitless 0–100 viewBox space. They are not pixels
 * and not design tokens; the token layer governs colour, type and spacing, and
 * a diamond's diagonals are none of those.
 */

/** 1–12, Mesha-first, matching `KundliHouse.rashi`. */
export type RashiIndex = number;

export interface Cell {
  /** SVG polygon points, viewBox units. */
  points: string;
  /** Where the label block sits, viewBox units. */
  labelX: number;
  labelY: number;
  /**
   * Top-left corner, for the south chart's lagna rule. Carried rather than
   * parsed back out of `points` — a geometry module that reads its own
   * strings is one refactor away from a chart whose lagna mark is in the
   * wrong box and whose type checker never noticed.
   */
  originX?: number;
  originY?: number;
}

/**
 * North Indian: a square, both diagonals, and the inner square joining the
 * side midpoints. Twelve regions — four central diamonds and eight corner
 * triangles — indexed 1–12 by HOUSE, counting anticlockwise from the top.
 */
export const NORTH_HOUSES: readonly Cell[] = [
  { points: "50,0 75,25 50,50 25,25", labelX: 50, labelY: 20 }, // 1  top diamond
  { points: "0,0 50,0 25,25", labelX: 25, labelY: 11 }, // 2  upper-left
  { points: "0,0 25,25 0,50", labelX: 11, labelY: 25 }, // 3  left-upper
  { points: "0,50 25,25 50,50 25,75", labelX: 20, labelY: 50 }, // 4  left diamond
  { points: "0,50 25,75 0,100", labelX: 11, labelY: 75 }, // 5  left-lower
  { points: "0,100 25,75 50,100", labelX: 25, labelY: 89 }, // 6  lower-left
  { points: "50,100 25,75 50,50 75,75", labelX: 50, labelY: 80 }, // 7  bottom diamond
  { points: "50,100 75,75 100,100", labelX: 75, labelY: 89 }, // 8  lower-right
  { points: "100,100 75,75 100,50", labelX: 89, labelY: 75 }, // 9  right-lower
  { points: "100,50 75,75 50,50 75,25", labelX: 80, labelY: 50 }, // 10 right diamond
  { points: "100,50 75,25 100,0", labelX: 89, labelY: 25 }, // 11 right-upper
  { points: "100,0 75,25 50,0", labelX: 75, labelY: 11 }, // 12 upper-right
] as const;

/** The lines drawn over the north chart: the square, both diagonals, the inner square. */
export const NORTH_LINES: readonly string[] = [
  "M0,0 L100,0 L100,100 L0,100 Z",
  "M0,0 L100,100",
  "M100,0 L0,100",
  "M50,0 L100,50 L50,100 L0,50 Z",
] as const;

/**
 * South Indian: a 4×4 grid with the middle 2×2 left empty, giving twelve cells
 * around the edge. The rashis are FIXED — Meena top-left, then clockwise — and
 * this array is indexed by rashi 1–12 (Mesha first), not by house.
 */
const SOUTH_GRID: readonly (readonly [number, number])[] = [
  [1, 0], // 1  Mesha
  [2, 0], // 2  Vrishabha
  [3, 0], // 3  Mithuna
  [3, 1], // 4  Karka
  [3, 2], // 5  Simha
  [3, 3], // 6  Kanya
  [2, 3], // 7  Tula
  [1, 3], // 8  Vrishchika
  [0, 3], // 9  Dhanu
  [0, 2], // 10 Makara
  [0, 1], // 11 Kumbha
  [0, 0], // 12 Meena
] as const;

const SOUTH_SIDE = 25;

export const SOUTH_CELLS: readonly Cell[] = SOUTH_GRID.map(([col, row]) => {
  const x = col * SOUTH_SIDE;
  const y = row * SOUTH_SIDE;
  return {
    points: `${x},${y} ${x + SOUTH_SIDE},${y} ${x + SOUTH_SIDE},${y + SOUTH_SIDE} ${x},${y + SOUTH_SIDE}`,
    labelX: x + SOUTH_SIDE / 2,
    labelY: y + 9,
    originX: x,
    originY: y,
  };
});

/** The south chart's outline: the outer square and the empty centre block. */
export const SOUTH_LINES: readonly string[] = [
  "M0,0 L100,0 L100,100 L0,100 Z",
  "M25,0 L25,100",
  "M50,0 L50,25 M50,75 L50,100",
  "M75,0 L75,100",
  "M0,25 L100,25",
  "M0,50 L25,50 M75,50 L100,50",
  "M0,75 L100,75",
] as const;

/**
 * The diagonal §24.3's south chart draws through the lagna's cell.
 *
 * The lagna has to be marked SOMEWHERE, and in the south tradition it is a
 * line across the corner of its square rather than a colour — which also
 * satisfies §29.4, since a state carried by colour alone is not carried at all.
 */
export function southLagnaMark(cell: Cell): string | null {
  const { originX, originY } = cell;
  if (originX === undefined || originY === undefined) return null;
  const half = SOUTH_SIDE / 2;
  return `M${originX},${originY} L${originX + half},${originY} L${originX},${originY + half} Z`;
}

export const VIEWBOX = "0 0 100 100";
