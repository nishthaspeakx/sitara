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
  | "reading_unavailable";

export interface SetupOptions {
  locale?: string;
  scenario?: Scenario;
  state?: Partial<StubState>;
}

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
      state: options.state ?? {},
    }),
  });
  if (!response.ok) throw new Error(`stub-api reset failed: ${response.status}`);

  await page.context().addCookies([
    { name: "sitara_test_client", value: clientId, domain: "127.0.0.1", path: "/" },
  ]);
  return clientId;
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
