import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

import {
  BRIEF_STATUSES,
  CONFIDENCE_STATES,
  DENSITIES,
  MORNING_MODULES,
  PLAN_STATES,
  TIERS,
  type TodayPayload,
} from "@sitara/schemas";

import { TODAY_VARIANTS } from "./_onboarding-fixtures";

/**
 * The guard on the recorded briefs.
 *
 * `services/api/scripts/record_today_fixtures.py` writes these from the real
 * pipeline, and `stub-api.mjs` replays them, so every §24.8 baseline and both
 * flow suites are pictures of genuine engine output. What that arrangement
 * cannot survive on its own is a recording that goes stale or is hand-edited:
 * a committed JSON file is a very easy thing to "just fix" when a test is red,
 * and the fix would be a fixture the engine could never produce.
 *
 * So every file is re-validated against the generated schema here — closed sets
 * are closed, required fields are present, and §30.4's fact IDs are absent. Pure
 * Node, no server: this runs in the `library` project.
 */

const DIR = path.join(__dirname, "__fixtures__", "today");

function load(): Array<{ file: string; payload: TodayPayload }> {
  return readdirSync(DIR)
    .filter((f) => f.endsWith(".json"))
    .map((file) => ({
      file,
      payload: JSON.parse(readFileSync(path.join(DIR, file), "utf-8")) as TodayPayload,
    }));
}

const LOCALES = ["en", "hi", "hi-Latn"] as const;

test.describe("recorded Today payloads", () => {
  test("every §28.2 variant is recorded in every launch locale", () => {
    const files = new Set(readdirSync(DIR));
    for (const variant of TODAY_VARIANTS) {
      for (const locale of LOCALES) {
        expect(files, `${variant}.${locale}.json`).toContain(`${variant}.${locale}.json`);
      }
    }
  });

  test("the two non-default densities are recorded too", () => {
    // §28.2: "density changes ranking-engine output count, never facts", so one
    // variant at each density is the property worth a baseline — not sixteen.
    const files = new Set(readdirSync(DIR));
    for (const density of ["low", "high"]) {
      for (const locale of LOCALES) {
        expect(files).toContain(`normal_morning_${density}.${locale}.json`);
      }
    }
  });

  test("every closed set is closed", () => {
    for (const { file, payload } of load()) {
      expect(DENSITIES, file).toContain(payload.density);
      expect(TIERS, file).toContain(payload.tier);
      expect(BRIEF_STATUSES, file).toContain(payload.status);
      expect(PLAN_STATES, file).toContain(payload.state.plan);
      if (payload.confidence) expect(CONFIDENCE_STATES, file).toContain(payload.confidence);

      for (const card of payload.modules) {
        // §34.3's enum is the whole point: a recording naming a module the
        // ranking engine may not emit would put a card on screen that the
        // product can never produce.
        expect(MORNING_MODULES, `${file}: ${card.module}`).toContain(card.module);
        expect(CONFIDENCE_STATES, file).toContain(card.confidence);
        expect(card.text.trim(), `${file}: ${card.module}`).not.toBe("");
      }
    }
  });

  test("no fact ID survives into a recording (§30.4)", () => {
    for (const { file, payload } of load()) {
      const raw = JSON.stringify(payload);
      // The marker the composer puts INSIDE each sentence, and the id grammar
      // itself. `strip_citations` runs in `presenter.py`; this is the proof it
      // ran on every line of every recording.
      expect(raw, file).not.toContain("[[");
      expect(raw, file).not.toMatch(/fact:[a-z_.]+\//);
    }
  });

  test("Tara's line is present on every morning, including the empty ones", () => {
    // §28.2 calls it "always present", and the recordings are where that claim
    // is cheapest to break: a first-session or failed brief has no modules, and
    // an anchor that only appears beside cards is not an anchor.
    for (const { file, payload } of load()) {
      expect(payload.taras_line, file).not.toBeNull();
      expect(payload.taras_line?.text.trim(), file).not.toBe("");
    }
  });

  test("the degraded recording really is degraded", () => {
    for (const locale of LOCALES) {
      const payload = JSON.parse(
        readFileSync(path.join(DIR, `provider_degraded.${locale}.json`), "utf-8"),
      ) as TodayPayload;

      // Not merely "a short brief". §7.1's degrade is a named outcome with a
      // named reason, and §5.4 puts it in the tradition-general state — "we can
      // tell you what the day holds generally, not what it holds for you".
      expect(payload.status).toBe("verified_core_cards");
      expect(payload.degrade_reason).not.toBeNull();
      expect(payload.confidence).toBe("tradition_based_general");

      // `ranking.core_cards` is deliberately narrower than LOW density.
      for (const card of payload.modules) {
        expect(
          ["moon_nakshatra_note", "energy_of_day", "personal_chart_theme"],
          `${locale}: ${card.module}`,
        ).toContain(card.module);
      }
    }
  });

  test("a Hindi recording is actually in Hindi (§2.4)", () => {
    // The recordings are the one place a silent English fallback would be
    // committed rather than merely rendered, and it would then be invisible in
    // every baseline taken from them.
    for (const variant of TODAY_VARIANTS) {
      const payload = JSON.parse(
        readFileSync(path.join(DIR, `${variant}.hi.json`), "utf-8"),
      ) as TodayPayload;
      const text = [payload.taras_line?.text ?? "", ...payload.modules.map((m) => m.text)].join(" ");
      if (text.trim()) expect(text, variant).toMatch(/[ऀ-ॿ]/);
    }
  });

  test("the density recordings differ in COUNT, not in facts (§28.2)", () => {
    const read = (name: string) =>
      JSON.parse(readFileSync(path.join(DIR, name), "utf-8")) as TodayPayload;

    const low = read("normal_morning_low.en.json");
    const med = read("normal_morning.en.json");
    const high = read("normal_morning_high.en.json");

    expect(low.modules.length).toBeLessThan(med.modules.length);
    expect(med.modules.length).toBeLessThanOrEqual(high.modules.length);

    // Every card LOW shows must read identically at MED and HIGH. Density that
    // changed a sentence would mean the engine had two versions of the day.
    const byId = new Map(high.modules.map((m) => [m.module, m.text]));
    for (const card of low.modules) {
      expect(byId.get(card.module), card.module).toBe(card.text);
    }
  });
});
