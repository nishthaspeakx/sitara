import type { Page, Route } from "@playwright/test";

/**
 * The stubbed backend the onboarding flow suites run against.
 *
 * It is a small STATE MACHINE, not a set of canned responses, because §24.4's
 * per-step persistence is the thing under test: a PATCH has to change what the
 * next GET returns, or "resume on return" would pass against a stub that
 * remembers nothing while failing against the real API.
 *
 * The live-path acceptance run (real Firebase, real sitara-api, real engine) is
 * what proves the other half — see docs/change-log.md for M8.
 */

export interface StubState {
  locale: string;
  completed_steps: number[];
  has_birth_details: boolean;
  time_accuracy: string | null;
  has_city: boolean;
  interest: string | null;
  priorities: string[];
  display_name: string | null;
  brief_time: string | null;
  voice_enabled: boolean;
}

export function emptyState(locale = "en"): StubState {
  return {
    locale,
    completed_steps: [],
    has_birth_details: false,
    time_accuracy: null,
    has_city: false,
    interest: null,
    priorities: [],
    display_name: null,
    brief_time: null,
    voice_enabled: true,
  };
}

const PLACES = [
  { id: "bengaluru", label: "Bengaluru", lat: 12.97, lon: 77.59, tz: "Asia/Kolkata" },
  { id: "mumbai", label: "Mumbai", lat: 19.08, lon: 72.88, tz: "Asia/Kolkata" },
  { id: "london", label: "London", lat: 51.51, lon: -0.13, tz: "Europe/London" },
];

/**
 * Term names as the REAL composer renders them.
 *
 * `reading.compose` fills every slot through `localised_term`, so a Hindi
 * reading carries रोहिणी and शुक्र — never the English name inside a Devanagari
 * sentence. A stub that returned "Rohini" for every locale would have baked
 * exactly that leak into the §24.8 screen baselines, making the picture §14's
 * Language QA is meant to catch into the picture it compares against.
 * `test_the_composer_renders_terms_in_the_asked_for_locale` is the Python side
 * of the same assertion.
 */
const TERMS: Record<string, { nakshatra: string; graha: string; paksha: string }> = {
  en: { nakshatra: "Rohini", graha: "Venus", paksha: "Shukla paksha" },
  hi: { nakshatra: "रोहिणी", graha: "शुक्र", paksha: "शुक्ल पक्ष" },
  "hi-Latn": { nakshatra: "Rohini", graha: "Shukra", paksha: "Shukla paksha" },
};

export function reading(locale = "en") {
  const terms = TERMS[locale] ?? TERMS.en!;
  return {
    status: "complete",
    confidence: "verified",
    source_state: "default",
    missing: [] as string[],
    degrade_reason: null,
    lines: [
      {
        id: "moon_nakshatra",
        values: { nakshatra: terms.nakshatra },
        fact_ids: ["natal.graha.nakshatra:moon:v1"],
        confidence: "verified",
        house: null,
      },
      {
        id: "observation",
        house: 7,
        values: { graha: terms.graha },
        fact_ids: ["natal.house_assignment:venus:v1"],
        confidence: "verified",
      },
      {
        id: "panchang",
        values: { tithi: "5", paksha: terms.paksha },
        fact_ids: ["panchang.tithi:2026-08-12:bengaluru"],
        confidence: "verified",
        house: null,
      },
    ],
    facts: [],
  };
}

/** Installs the whole stubbed backend and returns the mutable state. */
export async function stubBackend(page: Page, locale = "en"): Promise<StubState> {
  const state = emptyState(locale);

  await page.route("**/auth/session", (route: Route) =>
    route.fulfill({ json: { user_id: "6a70000000000000000000a1", is_new_user: true } }),
  );

  await page.route("**/v1/places*", (route: Route) => {
    const query = new URL(route.request().url()).searchParams.get("q")?.toLowerCase() ?? "";
    route.fulfill({
      json: PLACES.filter((p) => p.label.toLowerCase().startsWith(query)),
    });
  });

  await page.route("**/v1/onboarding/birth", async (route: Route) => {
    const body = route.request().postDataJSON();
    state.has_birth_details = true;
    state.time_accuracy = body.time_accuracy;
    if (!state.completed_steps.includes(7)) state.completed_steps.push(7);
    await route.fulfill({ json: state });
  });

  await page.route("**/v1/onboarding/consents", async (route: Route) => {
    if (!state.completed_steps.includes(5)) state.completed_steps.push(5);
    await route.fulfill({ json: state });
  });

  await page.route("**/v1/onboarding", async (route: Route) => {
    if (route.request().method() === "PATCH") {
      const body = route.request().postDataJSON();
      if (body.locale) state.locale = body.locale;
      if (body.interest) state.interest = body.interest;
      if (body.priorities) state.priorities = body.priorities;
      if (body.display_name) state.display_name = body.display_name;
      if (body.city) state.has_city = true;
      if (body.brief_time) state.brief_time = body.brief_time;
      if (typeof body.voice_enabled === "boolean") state.voice_enabled = body.voice_enabled;
      if (body.completed_step && !state.completed_steps.includes(body.completed_step)) {
        state.completed_steps.push(body.completed_step);
      }
    }
    await route.fulfill({
      json: { ...state, next_step: nextStep(state.completed_steps) },
    });
  });

  await page.route("**/v1/readings/first", (route: Route) =>
    route.fulfill({ json: reading(state.locale) }),
  );

  return state;
}

/** The stack is linear, so "next" is the lowest step not yet done (§28.1). */
export function nextStep(completed: number[]): number {
  for (let step = 2; step <= 13; step += 1) {
    if (!completed.includes(step)) return step;
  }
  return 13;
}

/**
 * S01 runs a real 1.2s canvas sequence. The suites that are not ABOUT the
 * launch force the static path so they spend their time on the stack rather
 * than on an animation whose own suite already covers it.
 */
export const SKIP_LAUNCH = "?launch=static";
