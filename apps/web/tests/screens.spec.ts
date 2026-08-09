import { expect, test, type Page } from "@playwright/test";

import { SKIP_LAUNCH, setupApi } from "./_onboarding-fixtures";

/**
 * Per-SCREEN, per-locale, per-theme baselines — the half of §24.8's design-QA
 * gate that `playwright.config.ts` used to say would "join when the §29.1
 * matrix is built". M8 built S01–S13, so it joins.
 *
 * The component suite already covers each component's states in isolation. What
 * it cannot see is what happens when they are composed: a Devanagari heading
 * that wraps into the card below it, a night-theme surface that swallows a
 * border, a Hinglish label 1.4× longer than its English baseline pushing a
 * control off a 390px viewport. Those are screen properties, and they are the
 * §14 Language-QA failures that actually reach users.
 *
 * 13 screens × 3 locales × 2 themes = 78 committed baselines.
 */

const SCREENS = [
  { id: "s01-launch", path: "/", ready: '[data-testid="launch-sequence"]' },
  { id: "s02-language", path: "/start/language" },
  { id: "s03-auth", path: "/start/auth" },
  { id: "s04-verify", path: "/start/verify" },
  { id: "s05-consent", path: "/start/consent" },
  { id: "s06-birth", path: "/start/birth" },
  { id: "s07-birth-time", path: "/start/birth/time" },
  { id: "s08-city", path: "/start/city" },
  { id: "s09-interest", path: "/start/interest" },
  { id: "s10-name", path: "/start/name" },
  { id: "s11-priorities", path: "/start/priorities" },
  { id: "s12-voice", path: "/start/voice" },
  { id: "s13-reading", path: "/start/reading", ready: '[data-testid="reading-line"]' },
] as const;

/** §2.4's launch three. The Tamil-length pseudo-locale stays on components:
 *  it is generated in the Storybook harness and is not a real catalog (§2.4). */
const LOCALES = ["en", "hi", "hi-Latn"] as const;
/** §24.2 light/reading and §34.8 night/dusk. */
const THEMES = ["light", "night"] as const;

/**
 * Two screens cannot be reached by URL, and that is the correct behaviour
 * rather than a testing inconvenience.
 *
 * S04 has nothing to verify without an OTP in flight, and S07 has no birth
 * date or place to attach a time to — both redirect to the question that comes
 * first, because §28.1 forbids landing a user on a blank form. So their
 * baselines are captured after walking the one step that precedes them, which
 * is how a user gets there too.
 */
const ARRIVE_VIA: Record<string, { path: string; walk: (page: Page) => Promise<void> }> = {
  "s04-verify": {
    path: "/start/auth",
    walk: async (page) => {
      await page.getByTestId("phone-input").fill("8130225222");
      await page.getByTestId("phone-continue").click();
      await page.waitForURL(/\/start\/verify$/);
    },
  },
  "s07-birth-time": {
    path: "/start/birth",
    walk: async (page) => {
      await page.getByTestId("birth-date").fill("1994-03-17");
      await page.getByRole("searchbox").fill("Beng");
      await page.getByTestId("place-results").getByText("Bengaluru").click();
      await page.getByTestId("birth-continue").click();
      await page.waitForURL(/\/start\/birth\/time$/);
    },
  },
};

/**
 * S07 renders differently once answered, and the answered layout is the one
 * worth diffing: unanswered, it hides both the clock field and the §5.4
 * confidence preview.
 */
async function prime(page: Page, id: string) {
  if (id === "s07-birth-time") {
    await page.getByTestId("accuracy-exact").locator("input").check();
    await page.getByTestId("birth-time").fill("06:45");
  }
  if (id === "s04-verify") {
    await page.getByTestId("otp-input").fill("123456");
  }
}

test.describe("§24.8 — screen baselines", () => {
  for (const screen of SCREENS) {
    for (const locale of LOCALES) {
      for (const theme of THEMES) {
        test(`${screen.id} · ${locale} · ${theme}`, async ({ page }) => {
          // S06/S07 need each other's answers, and S13 needs a finished stack,
          // so every screen is captured as a user who got there legitimately
          // would see it.
          await setupApi(page, {
            locale,
            state: {
              completed_steps: [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
              has_birth_details: true,
              time_accuracy: "exact",
            },
          });

          await page.addInitScript((t) => {
            document.documentElement.setAttribute("data-theme", t as string);
          }, theme);
          const via = ARRIVE_VIA[screen.id];
          await page.goto(`/${locale}${via?.path ?? screen.path}${SKIP_LAUNCH}`);
          if (via) await via.walk(page);
          // The theme attribute is re-applied after hydration replaces <html>'s
          // attributes on a client navigation.
          await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);

          if ("ready" in screen && screen.ready) {
            await page.locator(screen.ready).first().waitFor({ state: "visible" });
          }
          await prime(page, screen.id);
          await page.waitForLoadState("networkidle");
          // A skeleton mid-fade is the one thing guaranteed to differ run to
          // run; every screen settles before it is captured.
          await expect(page.locator('[aria-busy="true"]')).toHaveCount(0);

          await expect(page).toHaveScreenshot(`${screen.id}-${locale}-${theme}.png`, {
            fullPage: true,
          });
        });
      }
    }
  }
});
