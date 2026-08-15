import { defineConfig, devices } from "@playwright/test";

import { DIST_DIRS } from "./scripts/dist-dirs.mjs";

/**
 * §24.8's design-QA gate, both halves.
 *
 * The comment this file used to carry said the screen half "joins it when the
 * §29.1 matrix is built". M8 built S01–S13, so it joins now, and the config
 * grows from one project over Storybook to three over two servers:
 *
 *   library     the §24.3 manifest contract — pure Node, no server needed
 *   components  per-component × locale × theme baselines, over built Storybook
 *   screens     S01–S13 × 3 locales × 2 themes, plus the flow, back-navigation
 *               and ceremony-degradation suites, over a built Next app
 *
 * The screens server runs with `NEXT_PUBLIC_AUTH_ADAPTER=fake` so the flow tests
 * drive the real screens without a live Firebase project, and with a short
 * ceremony deadline so the S13 timeout path is testable in seconds rather than
 * in the six the product actually waits. Its `/auth` and `/v1` proxies point at
 * `scripts/stub-api.mjs` — a real process, so every API call travels the real
 * path through the locale middleware and the rewrite.
 */
const STORYBOOK_PORT = 6100;
const APP_PORT = 3100;
/** The stand-in for `sitara-api`. See scripts/stub-api.mjs for why it is a real
 *  process rather than a `page.route` intercept. */
const STUB_API_PORT = 3101;
/**
 * The stand-in for `sitara-realtime`. A REAL RFC 6455 server, for a reason
 * stronger than CL-013's: `page.route` cannot intercept a WebSocket at all, so
 * the only browser-side alternative would be replacing `window.WebSocket` — and
 * then the suite verifies that the client handles frames the test invented over
 * a transport that was never opened. The handshake, the close, the reconnect
 * and the ordering of frames against the DOM updates they cause would all be
 * invisible. See scripts/stub-realtime.mjs.
 */
const STUB_REALTIME_PORT = 3102;

/**
 * Which servers this run actually needs.
 *
 * Playwright starts every configured `webServer` regardless of which projects
 * are selected, and the `library` project needs neither: it reads files off
 * disk. Without this, `pnpm --filter web test` on a clean checkout waits for a
 * `next start` against a `.next-test` that has not been built yet — a hang with
 * no obvious cause, in the one command that is supposed to be cheap.
 */
function selectedProjects(argv: string[]): string[] {
  const names: string[] = [];
  argv.forEach((arg, i) => {
    if (arg.startsWith("--project=")) names.push(arg.slice("--project=".length));
    else if (arg === "--project" && argv[i + 1]) names.push(argv[i + 1]!);
  });
  return names;
}

const selected = selectedProjects(process.argv);
/** No `--project` means every project, so every server is needed. */
const needs = (project: string) => selected.length === 0 || selected.includes(project);

/**
 * The ceremony deadline the test BUILD carries (see `build:test`). Published to
 * the test process too, so the spec waits the same amount the screen does
 * instead of guessing.
 */
const CEREMONY_DEADLINE_MS = "1500";
process.env.NEXT_PUBLIC_CEREMONY_DEADLINE_MS = CEREMONY_DEADLINE_MS;

export default defineConfig({
  testDir: "./tests",
  outputDir: "./test-results",
  snapshotPathTemplate: "{testDir}/__screenshots__/{arg}{ext}",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: process.env.CI ? [["github"], ["list"]] : [["list"]],
  use: {
    deviceScaleFactor: 1,
  },
  expect: {
    toHaveScreenshot: {
      // CSS animations are frozen for the capture; the reduced-motion PATH is
      // covered by its own spec rather than by accidentally-stopped animation.
      animations: "disabled",
      caret: "hide",
      // The design-system faces are vendored into public/fonts and loaded by
      // src/app/fonts.css, so glyph rasterisation no longer varies with whatever
      // the machine happens to have installed. The remaining allowance covers
      // sub-pixel antialiasing only — it is NOT wide enough to hide a colour,
      // spacing or layout regression, which was the problem with 0.02.
      maxDiffPixelRatio: 0.001,
    },
  },
  webServer: [
    ...(needs("components")
      ? [{
          command: `node scripts/serve-static.mjs storybook-static ${STORYBOOK_PORT}`,
          url: `http://127.0.0.1:${STORYBOOK_PORT}/index.json`,
          // Never reused. A server left running from an earlier build serves
          // that build, and the suite reports on code nobody is looking at —
          // which is how a design-qa run failed 5 tests that pass in isolation,
          // against a `next start` from before the fix under test. A few
          // seconds of startup is cheaper than one such debugging session.
          reuseExistingServer: false,
          timeout: 60_000,
        }]
      : []),
    ...(needs("screens")
      ? [{
          command: `node scripts/stub-api.mjs ${STUB_API_PORT}`,
          url: `http://127.0.0.1:${STUB_API_PORT}/healthz`,
          reuseExistingServer: false,
          timeout: 30_000,
          env: {
            // The socket origin is SERVED to the client by
            // POST /v1/chat/session, never compiled into the app — so pointing
            // the suite at the stub is a server-side env var and needs no
            // rebuild. That is the same reason NEXT_PUBLIC_REALTIME_WS_URL was
            // removed.
            STUB_REALTIME_WS_URL: `ws://127.0.0.1:${STUB_REALTIME_PORT}/chat/session`,
            // §25.3's call socket is a separate path, as it is in the real
            // config: §6.1 scales and sticky-routes a minutes-long duplex
            // call independently of bursts of text.
            STUB_REALTIME_CALL_WS_URL: `ws://127.0.0.1:${STUB_REALTIME_PORT}/call/session`,
          },
        },
        {
          command: `node scripts/stub-realtime.mjs ${STUB_REALTIME_PORT}`,
          url: `http://127.0.0.1:${STUB_REALTIME_PORT}/healthz`,
          reuseExistingServer: false,
          timeout: 30_000,
        },
        {
          command: `pnpm exec next start --port ${APP_PORT}`,
          url: `http://127.0.0.1:${APP_PORT}/en`,
          reuseExistingServer: false,
          timeout: 120_000,
          env: {
            // The fake adapter and the short deadline are baked into the test
            // output by `build:test`; NEXT_DIST_DIR points `next start` at it.
            // `next dev` cannot be redirected this way — see next.config.ts.
            NEXT_DIST_DIR: DIST_DIRS.test,
            // NOTE: the proxy target is NOT settable here. Next evaluates
            // `rewrites()` at BUILD time and bakes the destination into
            // routes-manifest.json, so `build:test` is where
            // API_PROXY_TARGET=127.0.0.1:${STUB_API_PORT} is set. Setting it on
            // the server instead looks like it works and silently sends every
            // request to whatever the build baked in — which for a while was a
            // developer's real sitara-api on :8001, quietly passing tests that
            // were meant to be hermetic.
          },
        }]
      : []),
  ],
  projects: [
    {
      name: "library",
      testMatch:
        /library\.spec\.ts|tara-disclosure\.spec\.ts|dist-dirs\.spec\.ts|api-routing\.spec\.ts|today-variant\.spec\.ts|today-fixtures\.spec\.ts|chat-thread\.spec\.ts|voice-note\.spec\.ts|call-state\.spec\.ts|kundli-geometry\.spec\.ts|deletion-scope\.spec\.ts|chart-mapping\.spec\.ts/,
    },
    {
      name: "components",
      testMatch: /screenshots\.spec\.ts/,
      // 390×844 sits inside the 360–430 design target (§24.5)
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 390, height: 844 },
        baseURL: `http://127.0.0.1:${STORYBOOK_PORT}`,
      },
    },
    {
      name: "screens",
      // `today-variant` and `today-fixtures` are deliberately NOT here: they
      // read files off disk and belong to `library`, which needs no server. A
      // loose `today-.*` would run them twice and make the cheap command
      // wait on a `next start`.
      // M10 adds `deletion-confirm`, `journal-*`, `you-*` and `reflection`.
      // M11 adds `subscription-screens` (S30/S31/S34).
      // `deletion-scope` and `chart-mapping` are deliberately NOT here: they
      // read files off disk and belong to `library`, which needs no server. A
      // loose `deletion-.*` would run the scope spec twice and make the cheap
      // command wait on a `next start` — the trap `today-variant` already
      // documents.
      testMatch:
        /screens\.spec\.ts|onboarding-.*\.spec\.ts|ceremony-degradation\.spec\.ts|today-(empty|degraded|screens|routes)\.spec\.ts|ask-.*\.spec\.ts|call\.spec\.ts|deletion-confirm\.spec\.ts|journal-(screens|routes)\.spec\.ts|you-screens\.spec\.ts|subscription-screens\.spec\.ts|reflection\.spec\.ts/,
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 390, height: 844 },
        baseURL: `http://127.0.0.1:${APP_PORT}`,
      },
    },
  ],
});
