import { readFileSync } from "node:fs";
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { SKIP_LAUNCH, TODAY_VARIANTS, setupToday, type TodayVariant } from "./_onboarding-fixtures";

/**
 * §24.8's design-QA gate for S14 — §28.2's sixteen variants, in every launch
 * locale, in both themes.
 *
 * The component suite covers each component's states in isolation and the
 * S01–S13 suite covers screens the user walks through. Today is neither: it is
 * ONE screen with sixteen faces, and the interesting failures are compositional
 * — a festival banner and a grace banner competing for the space above the core
 * card, a Devanagari trial pill wrapping the practical strip onto a second row,
 * a night takeover whose dusk surface swallows the reflection prompt's border.
 * None of those is visible in a component story.
 *
 * What is captured, and why that shape:
 *
 *   16 variants × 3 locales × 2 themes   96   the matrix
 *   §32.1's worst case × 3 × 2            6   the rule's own named case
 *   LOW and HIGH density × 3              6   density changes COUNT (§28.2)
 *   reduced motion, night                 1   §0.12's collapsed path
 *                                       ───
 *                                       109
 *
 * Every payload behind these is REAL engine output, recorded from the pipeline
 * by `services/api/scripts/record_today_fixtures.py` and replayed by
 * `stub-api.mjs` over the real request path. A baseline of invented data would
 * stay green through any regression in ranking, composition or the §7.1 ladder.
 *
 * ── CL-013 ────────────────────────────────────────────────────────────────
 * No `page.route`, here or anywhere in this suite.
 */

const LOCALES = ["en", "hi", "hi-Latn"] as const;
const THEMES = ["light", "night"] as const;

async function settle(page: Page, theme: string) {
  // Re-applied after hydration replaces <html>'s attributes on a client nav.
  await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);
  await expect(page.getByTestId("today")).toBeVisible();
  // A skeleton mid-fade is the one thing guaranteed to differ run to run.
  await expect(page.locator('[aria-busy="true"]')).toHaveCount(0);
}

async function open(page: Page, locale: string, theme: string) {
  await page.addInitScript((t) => {
    document.documentElement.setAttribute("data-theme", t as string);
  }, theme);
  await page.goto(`/${locale}/today${SKIP_LAUNCH}`);
  await settle(page, theme);
}

/**
 * §28.2's OFFLINE variant is the screen's own state, not a payload.
 *
 * "cached brief + offline banner; practical strip marked 'as of [time]'" only
 * happens when a fetch FAILS over a cache that already holds a good morning —
 * so the setup has to reproduce both halves. Serving the offline fixture over a
 * healthy request, which is what this suite did at first, renders an ordinary
 * morning with `offline` written on the label: one of the sixteen never
 * exercised, and its baseline a picture of the wrong screen.
 *
 * Seeding `localStorage` is not an intercept — it is genuine client state, the
 * same state a previous successful visit would have left. The request still
 * travels the real path and really fails (CL-013).
 */
async function openOffline(page: Page, locale: string, theme: string) {
  const cached = JSON.parse(
    readFileSync(path.join(__dirname, "__fixtures__", "today", `offline.${locale}.json`), "utf-8"),
  );
  await page.addInitScript((t) => {
    document.documentElement.setAttribute("data-theme", t as string);
  }, theme);

  // Navigate FIRST. `localStorage` is per-origin and an init script runs on
  // `about:blank` too, so seeding it before the first navigation writes the
  // cache to an origin the app never reads — the screen then finds nothing and
  // renders the error state, which is how this was caught.
  await page.goto(`/${locale}/today${SKIP_LAUNCH}`);
  await page.evaluate(
    (payload) =>
      window.localStorage.setItem(
        "sitara.today.v1",
        // A FIXED time, so the "as of" stamp is data rather than the clock —
        // otherwise every offline baseline would differ by when CI ran.
        JSON.stringify({ payload, cachedAt: "07:12" }),
      ),
    cached,
  );
  await page.reload();
  await settle(page, theme);
}

test.describe("§24.8 — Today baselines", () => {
  for (const variant of TODAY_VARIANTS) {
    for (const locale of LOCALES) {
      for (const theme of THEMES) {
        test(`${variant} · ${locale} · ${theme}`, async ({ page }) => {
          if (variant === "offline") {
            // The stub really returns 503; the screen really falls back.
            await setupToday(page, { variant, locale, scenario: "today_unavailable" });
            await openOffline(page, locale, theme);
            await expect(page.getByTestId("today")).toHaveAttribute("data-variant", "offline");
            await expect(page.getByText("07:12")).toBeVisible();
          } else {
            await setupToday(page, { variant, locale });
            await open(page, locale, theme);
          }

          // §28.2's acceptance rule, checked on every capture rather than in
          // one test: "core card visually dominant in ALL variants". The night
          // takeover and the two brief-less variants have no core card at all,
          // which satisfies it differently — nothing is competing because
          // nothing is there.
          await expect(page.locator('[data-emphasis="core"]')).toHaveCount(
            NO_CORE_CARD.has(variant) ? 0 : 1,
          );

          await expect(page).toHaveScreenshot(`today-${variant}-${locale}-${theme}.png`, {
            fullPage: true,
          });
        });
      }
    }
  }
});

/**
 * The variants with no core card, and why each is correct rather than missing:
 *
 *  · `night`         — §28.2: "reflection CTA replaces core card position".
 *  · `first_session` — no brief exists; §5.3 forbids inventing one.
 *  · `offline`       — the cached payload IS a normal morning, so this one DOES
 *                      have a core card. It is not in the set.
 */
const NO_CORE_CARD = new Set<TodayVariant>(["night", "first_session"]);

test.describe("§32.1 — the worst-case stack", () => {
  // §32.1 names this combination explicitly: "The design-QA screenshot suite
  // adds the worst-case combination (grace+travel+festival+trial) per locale;
  // core-card dominance rule §28.2 verified against it."
  for (const locale of LOCALES) {
    for (const theme of THEMES) {
      test(`grace + travel + festival + trial · ${locale} · ${theme}`, async ({ page }) => {
        await setupToday(page, { variant: "worst_case", locale });
        await open(page, locale, theme);

        // Two banners and one pill — the ceiling, rendered.
        await expect(page.getByTestId("banner-grace")).toBeVisible();
        await expect(page.getByTestId("banner-travel")).toBeVisible();
        await expect(page.getByTestId("banner-festival")).toHaveCount(0);
        // The festival did not vanish; it moved to the core card.
        await expect(page.getByTestId("festival-accent")).toBeVisible();
        await expect(page.getByTestId("trial-pill")).toBeVisible();
        // §32.1: the birth-time chip yields to any banner.
        await expect(page.getByTestId("birth-time-chip")).toHaveCount(0);
        // And §28.2's rule still holds with three things above the fold.
        await expect(page.locator('[data-emphasis="core"]')).toHaveCount(1);

        await expect(page).toHaveScreenshot(`today-worst-case-${locale}-${theme}.png`, {
          fullPage: true,
        });
      });
    }
  }
});

test.describe("§28.2 — the density modes", () => {
  // Captured on `normal_morning` only: density changes the ranking engine's
  // output COUNT and never its facts, so sixteen variants × three densities
  // would be forty-eight baselines differing by two cards each.
  for (const density of ["low", "high"] as const) {
    for (const locale of LOCALES) {
      test(`${density} · ${locale}`, async ({ page }) => {
        await setupToday(page, { variant: "normal_morning", locale, density });
        await open(page, locale, "light");
        await expect(page.getByTestId("today")).toHaveAttribute("data-density", density);
        await expect(page).toHaveScreenshot(`today-density-${density}-${locale}.png`, {
          fullPage: true,
        });
      });
    }
  }
});

test("§0.12 — the night takeover under reduced motion", async ({ page }) => {
  await setupToday(page, { variant: "night" });
  await page.addInitScript(() => {
    document.documentElement.setAttribute("data-motion", "reduced");
    document.documentElement.setAttribute("data-theme", "night");
  });
  await page.goto(`/en/today${SKIP_LAUNCH}`);
  await page.evaluate(() => {
    document.documentElement.setAttribute("data-motion", "reduced");
    document.documentElement.setAttribute("data-theme", "night");
  });
  await settle(page, "night");
  await expect(page.getByTestId("night-takeover")).toBeVisible();
  await expect(page).toHaveScreenshot("today-night-reduced-motion.png", { fullPage: true });
});
