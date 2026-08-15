import { readFileSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

import { RASHI_ORDER, rashiIndex, toKundliHouses, type Chart } from "../src/lib/chart";

/**
 * The one translation between `/v1/chart` and `KundliChart`, in the `library`
 * project — no server, no browser.
 *
 * ── Why this is worth a spec of its own ───────────────────────────────────
 *
 * The API serves a rashi as a NAME; the diagram takes it as an index, because
 * CC-007's geometry places south-style cells by rashi. Something has to map
 * them, and the M6 lesson is what that something must not do:
 * `moon_nakshatra_note` took the first nakshatra-shaped value in a payload, the
 * engine emits one per graha with the Sun first, and the first live run printed
 * "The Moon sits in Purva Bhadrapada today" citing the SUN's nakshatra. Every
 * gate green. The id was in the served payload. The name matched the fact it
 * named. The sentence was false.
 *
 * A positional read here fails the same way and is harder to see, because a
 * chart drawn from shifted rashis is internally consistent and looks entirely
 * like a chart. The fixture below is built to FAIL one: the houses arrive OUT
 * OF ORDER, so any implementation that trusted array position would produce a
 * different diagram than one that resolved by name.
 */

const MESSAGES = path.join(__dirname, "..", "..", "..", "packages", "i18n", "messages");

test.describe("the rashi mapping (CC-007, and the M6 lesson)", () => {
  test("the zodiac is twelve unique names, Mesha first", () => {
    expect(RASHI_ORDER).toHaveLength(12);
    expect(new Set(RASHI_ORDER).size).toBe(12);
    expect(RASHI_ORDER[0]).toBe("mesha");
    // Mesha = 1 is the contract `KundliChart` documents; an off-by-one here
    // rotates every chart in the product by one sign.
    expect(rashiIndex("mesha")).toBe(1);
    expect(rashiIndex("meena")).toBe(12);
  });

  test("every rashi index has a label in every launch locale", () => {
    // §2.4. The diagram's boxes are the least forgiving place for a missing
    // key: a raw `ui.kundli.rashi.7` inside a triangle reads as a rendering bug
    // rather than as a translation gap, so nobody files it as one.
    for (const locale of ["en", "hi", "hi-Latn"]) {
      const catalog = JSON.parse(
        readFileSync(path.join(MESSAGES, `${locale}.json`), "utf-8"),
      ) as { ui: { kundli: { rashi: Record<string, string> } } };
      for (let index = 1; index <= 12; index += 1) {
        expect(catalog.ui.kundli.rashi[String(index)], `${locale}: rashi ${index}`).toBeTruthy();
      }
    }
  });

  test("placement is by NAME — the fixture is built to fail a positional read", () => {
    // Houses deliberately out of order and rashis deliberately not sequential.
    // A positional implementation would map house 1 to whatever is at index 0.
    const chart: Chart = {
      houses: [
        { house: 7, rashi: "kumbha", grahas: ["venus"], is_lagna: false },
        { house: 1, rashi: "simha", grahas: ["sun"], is_lagna: true },
        { house: 4, rashi: "vrishchika", grahas: ["moon"], is_lagna: false },
      ],
      lagna_rashi: "simha",
      confidence: "verified",
      moon_chart: false,
      unplaced: [],
    };

    const houses = toKundliHouses(chart);

    const first = houses.find((h) => h.house === 1);
    expect(first?.rashi).toBe(5); // simha, resolved by name
    expect(first?.isLagna).toBe(true);
    expect(houses.find((h) => h.house === 7)?.rashi).toBe(11); // kumbha
    expect(houses.find((h) => h.house === 4)?.rashi).toBe(8); // vrishchika

    // And the grahas travelled with their own house, not with a slot.
    expect(houses.find((h) => h.house === 1)?.grahas).toEqual(["sun"]);
    expect(houses.find((h) => h.house === 7)?.grahas).toEqual(["venus"]);
  });

  test("a rashi outside the closed set is DROPPED, never defaulted to Mesha", () => {
    // The caller resolved it from engine facts, so an impossible value means
    // the resolution is wrong. Drawing it in Mesha would hide that behind a
    // chart that looks fine — which is the failure mode this whole file is
    // about, arrived at by a different road.
    const chart = {
      houses: [
        { house: 1, rashi: "simha", grahas: [], is_lagna: true },
        { house: 2, rashi: "not_a_rashi", grahas: ["mars"], is_lagna: false },
      ],
      lagna_rashi: "simha",
      confidence: "verified",
      moon_chart: false,
      unplaced: [],
    } as unknown as Chart;

    const houses = toKundliHouses(chart);
    expect(houses).toHaveLength(1);
    expect(houses[0]?.house).toBe(1);
  });
});
