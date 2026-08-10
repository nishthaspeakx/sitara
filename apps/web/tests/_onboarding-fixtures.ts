import type { Page } from "@playwright/test";

/**
 * Test-side control of `scripts/stub-api.mjs`.
 *
 * There is deliberately NO `page.route` here any more. A browser-level
 * intercept stops the request before it leaves, so the Next server — and with
 * it the locale middleware and the `/v1` rewrite — never sees it. That is how
 * every onboarding step could 404 in a real browser with the whole flow suite
 * green: next-intl 307'd `/v1/onboarding` to `/hi/v1/onboarding`, and an
 * intercept can never observe a redirect issued by the server it prevented the
 * request from reaching.
 *
 * Now the requests go browser → `next start` → middleware → rewrite → stub, and
 * the tests configure the stub out-of-band on its own port. The stub is still a
 * state machine, because §24.4's per-step persistence is the thing under test:
 * a PATCH has to change what the next GET returns.
 */

const STUB = "http://127.0.0.1:3101";

export interface StubState {
  locale: string;
  /**
   * Whether `POST /auth/session` has run for this client.
   *
   * Everything under `/v1` is behind it, exactly as in `sitara_api` — a suite
   * whose stub granted onboarding writes to anonymous callers could not see
   * that S02 runs before auth and 401s in a real browser.
   */
  session_user_id: string | null;
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

/** What the stub can be told to do. Mirrors `scripts/stub-api.mjs`. */
export type Scenario =
  | "ok"
  | "fail_writes"
  | "auth_fails"
  | "reading_slow"
  | "reading_hangs"
  | "reading_no_birth_time"
  | "reading_engine_down_then_panchang"
  | "reading_no_panchang"
  | "reading_unavailable"
  | "today_unavailable";

/**
 * §28.2's sixteen. The ids are the recorded fixtures' filenames, so a variant
 * that has never been recorded from the real pipeline cannot be asked for.
 */
export const TODAY_VARIANTS = [
  "first_session",
  "first_morning",
  "normal_morning",
  "afternoon",
  "evening",
  "night",
  "festival",
  "birthday",
  "travel",
  "missing_birth_time",
  "offline",
  "provider_degraded",
  "trial",
  "premium",
  "free",
  "payment_grace",
] as const;
export type TodayVariant = (typeof TODAY_VARIANTS)[number];

/**
 * §32.1's own named screenshot case, recorded alongside the sixteen but not one
 * of them: "the design-QA screenshot suite adds the worst-case combination
 * (grace+travel+festival+trial) per locale". Kept out of `TODAY_VARIANTS` so
 * "§28.2's sixteen" keeps meaning sixteen.
 */
export const EXTRA_FIXTURES = ["worst_case"] as const;
export type FixtureName = TodayVariant | (typeof EXTRA_FIXTURES)[number];

export interface SetupOptions {
  locale?: string;
  scenario?: Scenario;
  state?: Partial<StubState>;
  /** Which recorded brief `/v1/today` replays. */
  variant?: FixtureName;
  /** §28.2's density. Recorded for `normal_morning` only. */
  density?: "low" | "med" | "high";
}

/** The id `POST /auth/session` mints, mirrored from `scripts/stub-api.mjs`. */
export const SIGNED_IN_USER = "6a70000000000000000000a1";

let counter = 0;

/**
 * Give this page its own bucket in the stub and configure it.
 *
 * The bucket is keyed by a cookie on the APP origin — Next's rewrite forwards
 * cookies to the proxy target, so parallel workers cannot collide.
 */
export async function setupApi(page: Page, options: SetupOptions = {}): Promise<string> {
  const clientId = `c${process.pid}-${(counter += 1)}`;
  const response = await fetch(`${STUB}/__control/reset`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      clientId,
      locale: options.locale ?? "en",
      scenario: options.scenario ?? "ok",
      // Most specs describe a SIGNED-IN user, because most screens are behind
      // the §34.5 session — so that is the default, and a spec about the
      // pre-auth world (S02 runs before auth) opts out with
      // `state: { session_user_id: null }`. Before the stub had this gate it
      // granted onboarding writes to anonymous callers, and the suite could not
      // see that S02 401s in a real browser.
      state: { session_user_id: SIGNED_IN_USER, ...(options.state ?? {}) },
      variant: options.variant ?? "normal_morning",
      density: options.density ?? "med",
    }),
  });
  if (!response.ok) throw new Error(`stub-api reset failed: ${response.status}`);

  await page.context().addCookies([
    { name: "sitara_test_client", value: clientId, domain: "127.0.0.1", path: "/" },
  ]);
  return clientId;
}

/**
 * Re-configure a client mid-test — switching a scenario on once a screen is in
 * position, without losing what it already had.
 *
 * A spec that called `/__control/reset` directly had to remember to re-send
 * `session_user_id`, and forgetting it turned every "failed write" into a 401:
 * non-retryable, so `ErrorState` renders no retry control at all and the test
 * fails for a reason unrelated to what it is testing. The defaulting belongs in
 * one place.
 */
export async function setScenario(
  clientId: string,
  scenario: Scenario,
  state: Partial<StubState> = {},
): Promise<void> {
  const response = await fetch(`${STUB}/__control/reset`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      clientId,
      scenario,
      state: { session_user_id: SIGNED_IN_USER, ...state },
    }),
  });
  if (!response.ok) throw new Error(`stub-api reset failed: ${response.status}`);
}

/** Read the stub's view of a client — for asserting a step actually persisted. */
export async function serverState(clientId: string): Promise<StubState> {
  const response = await fetch(`${STUB}/__control/state?clientId=${encodeURIComponent(clientId)}`);
  return (await response.json()) as StubState;
}

/**
 * S01 runs a real 1.2s canvas sequence. Suites that are not ABOUT the launch
 * force the static path so they spend their time on the stack instead.
 */
export const SKIP_LAUNCH = "?launch=static";

/**
 * A client who finished onboarding, pointed at one recorded morning.
 *
 * Today is a post-onboarding surface, so every one of its specs needs the same
 * completed stack; only the variant differs. Same `setupApi` underneath — same
 * real request path, still no `page.route` anywhere.
 */
export async function setupToday(
  page: Page,
  options: {
    locale?: string;
    variant?: FixtureName;
    scenario?: Scenario;
    density?: "low" | "med" | "high";
  } = {},
): Promise<string> {
  return setupApi(page, {
    locale: options.locale ?? "en",
    scenario: options.scenario ?? "ok",
    variant: options.variant ?? "normal_morning",
    density: options.density ?? "med",
    state: {
      completed_steps: [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13],
      has_birth_details: true,
      has_city: true,
      time_accuracy: "exact",
      brief_time: "07:00",
    },
  });
}
