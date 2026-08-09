import { defineConfig, devices } from "@playwright/test";

/**
 * The per-locale screenshot-diff suite (§14 Language QA, gated by §24.8).
 *
 * §24.8: "the per-locale screenshot-diff suite runs on component stories
 * (Storybook) AND full screens." This config covers the component half; the
 * screen half joins it when the §29.1 matrix is built.
 *
 * It runs against the BUILT Storybook, served by a dependency-free static
 * server, so a CI run fetches nothing at test time.
 */
const PORT = 6100;

export default defineConfig({
  testDir: "./tests",
  outputDir: "./test-results",
  snapshotPathTemplate: "{testDir}/__screenshots__/{arg}{ext}",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: process.env.CI ? [["github"], ["list"]] : [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
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
  webServer: {
    command: `node scripts/serve-static.mjs storybook-static ${PORT}`,
    url: `http://127.0.0.1:${PORT}/index.json`,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
  projects: [
    {
      name: "chromium",
      // 390×844 sits inside the 360–430 design target (§24.5)
      use: { ...devices["Desktop Chrome"], viewport: { width: 390, height: 844 } },
    },
  ],
});
