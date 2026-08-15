/**
 * The natal chart, from `/v1/chart` to `KundliChart`'s props.
 *
 * ── The one translation this module performs, and why it is by NAME ────────
 *
 * The API serves a rashi as its NAME (`"simha"`); `KundliChart` takes it as an
 * index 1–12 with Mesha = 1, because the diagram's geometry is positional —
 * south-style cells are indexed by rashi, and CC-007's `kundli-geometry.ts`
 * places by that index.
 *
 * So something has to map one to the other, and it maps by NAME, never by the
 * position of the house in the response array. That is the M6 lesson in its
 * smallest possible form: `moon_nakshatra_note` took the first nakshatra-shaped
 * value in a payload, the engine emits one per graha with the Sun first, and
 * the first live run printed "The Moon sits in Purva Bhadrapada today" citing
 * the SUN's nakshatra — every gate green, and the sentence false. A positional
 * read here would draw a chart that is internally consistent, plausible, and
 * wrong to the one user who has had hers on paper for forty years.
 *
 * `RASHI_ORDER` is the §5 zodiac, Mesha-first — the same closed set and the
 * same order as `sitara_schemas.facts.Rashi`. It is declared rather than
 * derived because there is no generated JS schema for it; `tests/chart.spec.ts`
 * asserts it is twelve unique names and that each maps to a catalog label, so a
 * typo fails a gate rather than rendering an empty box.
 */

import type { Graha, KundliHouse } from "@/components/ui";

import { apiCall, type ApiResult } from "./api";

export const RASHI_ORDER = [
  "mesha",
  "vrishabha",
  "mithuna",
  "karka",
  "simha",
  "kanya",
  "tula",
  "vrishchika",
  "dhanu",
  "makara",
  "kumbha",
  "meena",
] as const;
export type Rashi = (typeof RASHI_ORDER)[number];

export interface ChartHouse {
  house: number;
  rashi: Rashi;
  grahas: Graha[];
  is_lagna: boolean;
}

export interface Chart {
  houses: ChartHouse[];
  lagna_rashi: Rashi;
  /** §5.4 — on the ARTEFACT, not beside it. A diamond drawn from a guessed
   *  ascendant is a confident-looking lie. */
  confidence: string;
  /** True in Moon-chart mode: the first house is chandra lagna, not the
   *  ascendant, and the client must say so rather than draw an ordinary kundli
   *  with a quieter label. */
  moon_chart: boolean;
  /** Grahas the engine placed nowhere. A chart missing one says so instead of
   *  drawing eight as nine. */
  unplaced: Graha[];
}

/**
 * `subjectId` names a family member; omitted, it is the account-holder's own
 * chart. §30.5 keeps family guidance in the account-holder's spaces, and the
 * API is scoped to her — a member id that is not hers resolves to no birth
 * details rather than to somebody else's chart.
 */
export function loadChart(options: {
  localDate: string;
  subjectId?: string;
  timezone?: string;
}): Promise<ApiResult<Chart>> {
  const params = new URLSearchParams({ local_date: options.localDate });
  if (options.timezone) params.set("timezone", options.timezone);
  if (options.subjectId) params.set("subject_id", options.subjectId);
  return apiCall<Chart>(`/v1/chart?${params.toString()}`);
}

/** Mesha = 1. Returns 0 for a name outside the closed set — see `toKundliHouses`. */
export function rashiIndex(rashi: string): number {
  return RASHI_ORDER.indexOf(rashi as Rashi) + 1;
}

/**
 * The API's houses as the diagram's.
 *
 * A house whose rashi is not one of the twelve is DROPPED rather than defaulted
 * to Mesha. `KundliChart` already skips an out-of-range rashi for the same
 * reason: the caller resolved it from engine facts, so an impossible value
 * means the resolution is wrong, and drawing it in Mesha would hide that behind
 * a chart that looks fine.
 */
export function toKundliHouses(chart: Chart): KundliHouse[] {
  return chart.houses
    .map((house) => ({
      house: house.house,
      rashi: rashiIndex(house.rashi),
      grahas: house.grahas,
      isLagna: house.is_lagna,
    }))
    .filter((house) => house.rashi >= 1 && house.rashi <= 12);
}
