import { expect, test, type Page } from "@playwright/test";

import { SKIP_LAUNCH, setupToday } from "./_onboarding-fixtures";

/**
 * §29.1's three Today sub-routes — S15 why-this, S16 timings, S17 festival.
 *
 * They are one screen's worth of surface between them, but each carries a rule
 * that is easy to lose and impossible to see in a component story:
 *
 *   S16  §30.2 — the place a timing was computed for is never implied.
 *   S17  §5.2  — amanta and purnimanta date the same festival differently, so
 *                the reckoning is stated rather than assumed.
 *   S15  §30.4 — three layers, and no fact ID among them.
 *
 * 3 routes × 3 locales × 2 themes = 18 baselines, plus the behavioural checks
 * below. No `page.route` (CL-013).
 */

const LOCALES = ["en", "hi", "hi-Latn"] as const;
const THEMES = ["light", "night"] as const;

const ROUTES = [
  { id: "s16-timings", path: "/today/timings", ready: '[data-testid="timings"]', variant: "normal_morning" },
  { id: "s17-festival", path: "/today/festival", ready: '[data-testid="festival"]', variant: "festival" },
  {
    id: "s15-why",
    path: "/today/brief/personal_chart_theme/why",
    ready: '[data-testid="why"]',
    variant: "normal_morning",
  },
] as const;

async function open(page: Page, locale: string, theme: string, path: string, ready: string) {
  await page.addInitScript((t) => {
    document.documentElement.setAttribute("data-theme", t as string);
  }, theme);
  await page.goto(`/${locale}${path}${SKIP_LAUNCH}`);
  await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);
  await page.locator(ready).first().waitFor({ state: "visible" });
  await expect(page.locator('[aria-busy="true"]')).toHaveCount(0);
}

test.describe("§29.1 — the Today sub-routes", () => {
  for (const route of ROUTES) {
    for (const locale of LOCALES) {
      for (const theme of THEMES) {
        test(`${route.id} · ${locale} · ${theme}`, async ({ page }) => {
          await setupToday(page, { variant: route.variant, locale });
          await open(page, locale, theme, route.path, route.ready);
          await expect(page).toHaveScreenshot(`${route.id}-${locale}-${theme}.png`, {
            fullPage: true,
          });
        });
      }
    }
  }
});

test.describe("S16 — the day's timings", () => {
  test("names the place the timings were computed for (§30.2)", async ({ page }) => {
    await setupToday(page, { variant: "normal_morning" });
    await open(page, "en", "light", "/today/timings", '[data-testid="timings"]');
    // A timings screen without a place is wrong for every traveller, and the
    // timezone is not a substitute — nobody chose "Asia/Kolkata" as a city.
    await expect(page.getByText("Bengaluru")).toBeVisible();
  });

  test("draws every window the brief carried", async ({ page }) => {
    await setupToday(page, { variant: "normal_morning" });
    await open(page, "en", "light", "/today/timings", '[data-testid="timings"]');
    await expect(page.getByText("09:00–10:30")).toBeVisible();
    await expect(page.getByText("11:45–12:35")).toBeVisible();
  });

  test("never reaches for alarm colour on the care band (§29.2, §24.2)", async ({ page }) => {
    await setupToday(page, { variant: "normal_morning" });
    await open(page, "en", "light", "/today/timings", '[data-testid="timings"]');
    // "inauspicious" is a fact about the sky; amber, never red. The band is
    // read from computed style so a re-aliased token cannot hide a regression.
    const danger = ["#B3261E", "#C4564C", "#CD7169", "#B4453B"];
    const colours = await page.locator('[data-testid="timings"] *').evaluateAll((nodes) =>
      nodes.flatMap((n) => {
        const s = getComputedStyle(n);
        return [s.backgroundColor, s.borderColor, s.color];
      }),
    );
    const hex = (rgb: string) => {
      const m = rgb.match(/\d+/g);
      if (!m) return "";
      return `#${m.slice(0, 3).map((v) => Number(v).toString(16).padStart(2, "0")).join("")}`.toUpperCase();
    };
    for (const value of colours) expect(danger).not.toContain(hex(value));
  });

  test("the panchang row on Today actually reaches it", async ({ page }) => {
    await setupToday(page, { variant: "normal_morning" });
    await page.goto(`/en/today${SKIP_LAUNCH}`);
    await page.getByTestId("panchang-link").click();
    await expect(page).toHaveURL(/\/en\/today\/timings$/);
    await expect(page.getByTestId("timings")).toBeVisible();
  });
});

test.describe("S17 — today's observance", () => {
  test("states the reckoning that dated it (§5.2)", async ({ page }) => {
    await setupToday(page, { variant: "festival" });
    await open(page, "en", "light", "/today/festival", '[data-testid="festival"]');
    // amanta and purnimanta place the same festival on different days; a date
    // with no calendar beside it is a claim we have not qualified.
    await expect(page.getByTestId("festival-tradition")).toBeVisible();
    await expect(page.getByTestId("festival-tradition")).toContainText("Amanta");
  });

  test("names the festival in the user's own language (§2.4)", async ({ page }) => {
    await setupToday(page, { variant: "festival", locale: "hi" });
    await open(page, "hi", "light", "/today/festival", '[data-testid="festival"]');
    // Twice on this screen — the banner names it and the observance card says
    // what falls today — so the assertion is scoped rather than loosened. Both
    // are Devanagari; §2.4 has no exception for a proper noun.
    await expect(page.getByTestId("festival-banner")).toContainText("रक्षाबंधन");
    await expect(page.getByText("आज रक्षाबंधन है।")).toBeVisible();
  });

  test("says so plainly when no observance falls today", async ({ page }) => {
    await setupToday(page, { variant: "normal_morning" });
    await open(page, "en", "light", "/today/festival", '[data-testid="festival"]');
    await expect(page.getByTestId("festival-empty")).toBeVisible();
  });
});

test.describe("S15 — why this guidance", () => {
  test("renders §30.4's three layers", async ({ page }) => {
    await setupToday(page, { variant: "normal_morning" });
    await open(page, "en", "light", "/today/brief/personal_chart_theme/why", '[data-testid="why"]');

    const sheet = page.getByRole("dialog");
    await expect(sheet).toBeVisible();
    // (1) plain language, (2) the sources row + chip, (3) the specifics.
    await expect(sheet).toContainText(/computed from your chart/i);
    await expect(sheet.getByText("Verified", { exact: false }).first()).toBeVisible();
    await expect(sheet.getByRole("listitem").first()).toBeVisible();
  });

  test("layer 3 is the snapshot's VALUE, not a paraphrase of the card", async ({ page }) => {
    await setupToday(page, { variant: "normal_morning" });
    await open(page, "en", "light", "/today/brief/moon_nakshatra_note/why", '[data-testid="why"]');
    // The card says "The Moon sits in Rohini today"; the detail says what the
    // fact holds. A detail that merely restated the sentence would be a summary
    // dressed as a source.
    await expect(page.getByRole("dialog").getByRole("listitem").first()).toContainText("Rohini");
  });

  test("no fact ID reaches the reader (§30.4)", async ({ page }) => {
    await setupToday(page, { variant: "normal_morning" });
    await open(page, "en", "light", "/today/brief/personal_chart_theme/why", '[data-testid="why"]');
    const body = await page.locator("body").innerText();
    expect(body).not.toContain("[[");
    expect(body).not.toMatch(/fact:[a-z_.]+\//);
  });

  test("the card's own Why-this affordance reaches it", async ({ page }) => {
    await setupToday(page, { variant: "normal_morning" });
    await page.goto(`/en/today${SKIP_LAUNCH}`);
    // §30.4: "every astrological claim reachable to a Trust Sheet in ≤1 tap".
    // On Today that is the inline sheet; this asserts the same content is
    // reachable, which is what makes the route a real destination.
    await page.locator('[data-emphasis="core"]').getByTestId("why-this").click();
    await expect(page.getByRole("dialog")).toBeVisible();
  });

  test("a card that is not on today's brief is an honest miss, not a 404", async ({ page }) => {
    await setupToday(page, { variant: "provider_degraded" });
    await open(page, "en", "light", "/today/brief/relationship/why", '[data-testid="why"]');
    // The brief changes every morning; yesterday's link is a stale reference,
    // and a 404 would blame the user for the calendar.
    await expect(page.getByTestId("why-missing")).toBeVisible();
  });

  test("a card id the engine may not emit is rejected at the route", async ({ page }) => {
    await setupToday(page, { variant: "normal_morning" });
    await open(page, "en", "light", "/today/brief/not_a_module/why", '[data-testid="why"]');
    await expect(page.getByTestId("why")).toHaveAttribute("data-card", "unknown");
    await expect(page.getByTestId("why-missing")).toBeVisible();
  });
});
