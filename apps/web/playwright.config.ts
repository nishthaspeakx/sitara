import { defineConfig, devices } from "@playwright/test";

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
 * in the six the product actually waits.
 */
const STORYBOOK_PORT = 6100;
const APP_PORT = 3100;

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
    {
      command: `node scripts/serve-static.mjs storybook-static ${STORYBOOK_PORT}`,
      url: `http://127.0.0.1:${STORYBOOK_PORT}/index.json`,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
    {
      command: `pnpm exec next start --port ${APP_PORT}`,
      url: `http://127.0.0.1:${APP_PORT}/en`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      // The fake adapter and the short deadline are baked into `.next-test`
      // by `build:test`; NEXT_DIST_DIR is what points `next start` at it.
      env: { NEXT_DIST_DIR: ".next-test" },
    },
  ],
  projects: [
    {
      name: "library",
      testMatch: /library\.spec\.ts|tara-disclosure\.spec\.ts/,
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
      testMatch: /screens\.spec\.ts|onboarding-.*\.spec\.ts|ceremony-degradation\.spec\.ts/,
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 390, height: 844 },
        baseURL: `http://127.0.0.1:${APP_PORT}`,
      },
    },
  ],
});
