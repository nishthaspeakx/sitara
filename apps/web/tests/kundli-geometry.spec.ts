import { expect, test } from "@playwright/test";

import {
  NORTH_HOUSES,
  NORTH_LINES,
  SOUTH_CELLS,
  SOUTH_LINES,
  southLagnaMark,
} from "../src/components/ui/kundli-geometry";

/**
 * The two kundli layouts (§24.3, CC-007), in the `library` project — no server,
 * no browser, no Storybook.
 *
 * A screenshot proves the diagram LOOKS like a kundli. These prove it is the
 * RIGHT one: that the two traditions place by different keys, that the twelve
 * regions tile their square without gaps or overlaps, and that Mesha sits where
 * a south-Indian reader expects to find it. A diamond with its houses running
 * clockwise is a perfectly pretty picture and completely unreadable to the
 * person it was drawn for, and no pixel diff would ever say so.
 */

test.describe("§24.3 / CC-007 — the two kundli traditions", () => {
  test("both layouts have exactly twelve regions", () => {
    expect(NORTH_HOUSES).toHaveLength(12);
    expect(SOUTH_CELLS).toHaveLength(12);
  });

  test("the north chart's twelve regions tile the square exactly", () => {
    // Shoelace area of each polygon, summed. The square is 100×100, so twelve
    // regions that tile it sum to 10 000 — gaps and overlaps both fail.
    const area = NORTH_HOUSES.reduce((total, cell) => {
      const points = cell.points.split(" ").map((pair) => {
        const [x, y] = pair.split(",").map(Number);
        return [x ?? 0, y ?? 0] as const;
      });
      let sum = 0;
      for (let i = 0; i < points.length; i += 1) {
        const a = points[i]!;
        const b = points[(i + 1) % points.length]!;
        sum += a[0] * b[1] - b[0] * a[1];
      }
      return total + Math.abs(sum) / 2;
    }, 0);

    expect(area).toBeCloseTo(10_000, 6);
  });

  test("north house 1 is the top-centre diamond", () => {
    // The fixed point of the whole tradition: whatever the lagna, house 1 is
    // drawn here. A chart that moved it would be a south chart wearing a
    // diamond.
    const first = NORTH_HOUSES[0]!;
    expect(first.points).toBe("50,0 75,25 50,50 25,25");
    expect(first.labelX).toBe(50);
    expect(first.labelY).toBeLessThan(50);
  });

  test("north houses run anticlockwise from the top", () => {
    // House 4 is the LEFT diamond and house 10 the right — the direction that
    // separates a kundli from a mirror image of one.
    expect(NORTH_HOUSES[3]!.labelX).toBeLessThan(50);
    expect(NORTH_HOUSES[9]!.labelX).toBeGreaterThan(50);
    expect(NORTH_HOUSES[6]!.labelY).toBeGreaterThan(50); // house 7 at the bottom
  });

  test("the south chart's rashis are fixed, Meena top-left and Mesha beside it", () => {
    // The south tradition's own fixed point. SOUTH_CELLS is indexed by RASHI,
    // so index 11 is Meena and index 0 is Mesha.
    const meena = SOUTH_CELLS[11]!;
    const mesha = SOUTH_CELLS[0]!;
    expect([meena.originX, meena.originY]).toEqual([0, 0]);
    expect([mesha.originX, mesha.originY]).toEqual([25, 0]);
  });

  test("the south rashis run clockwise around the edge", () => {
    // Mesha → Vrishabha → Mithuna across the top, then down the right side.
    expect(SOUTH_CELLS[1]!.originX).toBe(50);
    expect(SOUTH_CELLS[2]!.originX).toBe(75);
    expect(SOUTH_CELLS[3]!.originY).toBe(25);
    expect(SOUTH_CELLS[8]!.originX).toBe(0); // Dhanu, bottom-left corner
  });

  test("the south chart leaves its centre empty", () => {
    // The 2×2 middle is not a cell. Every cell must touch an edge.
    for (const cell of SOUTH_CELLS) {
      const touchesEdge =
        cell.originX === 0 ||
        cell.originY === 0 ||
        cell.originX === 75 ||
        cell.originY === 75;
      expect(touchesEdge).toBe(true);
    }
  });

  test("the two traditions place by different keys, which is the whole point", () => {
    // North is indexed by house, south by rashi. Same twelve boxes, different
    // meaning — CC-007's "neither is a fallback for the other" is structural,
    // not a matter of styling.
    expect(NORTH_HOUSES[0]!.points).not.toBe(SOUTH_CELLS[0]!.points);
    // The diamond's defining feature is its two corner-to-corner diagonals.
    // The south chart is a grid and has none — checked as whole paths, since
    // both charts' outer squares legitimately pass through 100,100.
    expect(NORTH_LINES).toContain("M0,0 L100,100");
    expect(NORTH_LINES).toContain("M100,0 L0,100");
    expect(SOUTH_LINES).not.toContain("M0,0 L100,100");
    expect(SOUTH_LINES).not.toContain("M100,0 L0,100");
  });

  test("the lagna mark is a corner rule, not a fill", () => {
    // §29.4: no state by colour alone. A stroked corner survives greyscale,
    // a tinted cell does not.
    const mark = southLagnaMark(SOUTH_CELLS[0]!);
    expect(mark).toBe("M25,0 L37.5,0 L25,12.5 Z");
  });

  test("a cell with no origin yields no lagna mark rather than a wrong one", () => {
    // The north cells carry no origin — asking for a south mark on one is a
    // caller error, and returning null is how it stays visible instead of
    // drawing a rule through the wrong box.
    expect(southLagnaMark(NORTH_HOUSES[0]!)).toBeNull();
  });
});
