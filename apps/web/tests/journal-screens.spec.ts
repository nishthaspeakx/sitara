import { expect, test, type Page } from "@playwright/test";

import { SEED, SKIP_LAUNCH, setupRecords } from "./_onboarding-fixtures";

/**
 * §24.8's screen baselines for M10's Journal half — S21–S24.
 *
 * 4 surfaces × 3 locales × 2 themes = 24, plus the empty states and one
 * reduced-motion capture. `you-screens.spec.ts` carries the other five.
 *
 * ── Why every locale and not a representative one ─────────────────────────
 *
 * §24.2 gives each script its own size factor, line-height, tracking and Noto
 * family, applied by `data-script` on `<html>`. Devanagari sets taller and
 * wider than Latin at the same nominal size, so a row that fits in English can
 * clip in Hindi and wrap to three lines in Hinglish — and none of that fails a
 * typecheck, a lint or a behavioural test. The call baselines earned their
 * place on their first run by catching exactly this class of defect (a
 * letterboxed portrait, an illegible disclosure, two invisible controls); these
 * screens are denser than that one.
 *
 * Both themes for the same reason `today/sky.ts` and the call screen record at
 * length: `text-inverse` means "the opposite of THIS THEME's ink", so a token
 * that reads correctly in light can render navy-on-navy at night. That has been
 * walked into twice in this codebase, and each time the first night baseline is
 * what caught it.
 *
 * No `page.route` (CL-013) — every screen here is drawn from a real request
 * through the locale middleware and the `/v1` rewrite.
 */

const LOCALES = ["en", "hi", "hi-Latn"] as const;
const THEMES = ["light", "night"] as const;

const SURFACES = [
  { id: "s21-journal", path: "/journal", ready: '[data-testid="journal"]' },
  { id: "s22-journal-day", path: "/journal/2026-08-14", ready: '[data-testid="journal-day"]' },
  { id: "s23-journal-search", path: "/journal/search", ready: '[data-testid="journal-search"]' },
  { id: "s24-reflection", path: "/today/reflection", ready: '[data-testid="reflection"]' },
] as const;

async function open(
  page: Page,
  locale: string,
  theme: string,
  path: string,
  ready: string,
  motion?: "reduced",
): Promise<void> {
  await page.addInitScript(
    ({ t, m }) => {
      document.documentElement.setAttribute("data-theme", t as string);
      if (m) document.documentElement.setAttribute("data-motion", m as string);
    },
    { t: theme, m: motion ?? null },
  );
  await page.goto(`/${locale}${path}${SKIP_LAUNCH}`);
  await page.evaluate(
    ({ t, m }) => {
      document.documentElement.setAttribute("data-theme", t);
      if (m) document.documentElement.setAttribute("data-motion", m);
    },
    { t: theme, m: motion ?? null },
  );
  await page.locator(ready).first().waitFor({ state: "visible" });
  await expect(page.locator('[aria-busy="true"]')).toHaveCount(0);
}

test.describe("§29.1 — S21–S24, the Journal and the night", () => {
  for (const surface of SURFACES) {
    for (const locale of LOCALES) {
      for (const theme of THEMES) {
        test(`${surface.id} · ${locale} · ${theme}`, async ({ page }) => {
          await setupRecords(page, { locale });
          await open(page, locale, theme, surface.path, surface.ready);
          await expect(page).toHaveScreenshot(`${surface.id}-${locale}-${theme}.png`, {
            fullPage: true,
          });
        });
      }
    }
  }
});

test.describe("§24.6 — the Journal's designed empty states", () => {
  test("s21-journal-empty", async ({ page }) => {
    // A new account, not a failed request. §24.6 gives this its own designed
    // state with its own action, because "your journal begins with your first
    // morning" is a true and kind sentence and a blank page is neither.
    await setupRecords(page, { scenario: "records_empty" });
    await open(page, "en", "light", "/journal", '[data-testid="journal"]');
    await expect(page).toHaveScreenshot("s21-journal-empty-en-light.png", { fullPage: true });
  });

  test("s22-journal-day-empty", async ({ page }) => {
    // A quiet Tuesday is a DAY, not a 404 — the API says so and the screen
    // has to agree, because the timeline links to dates.
    await setupRecords(page, { scenario: "records_empty" });
    await open(page, "en", "light", "/journal/2026-08-13", '[data-testid="journal-day"]');
    await expect(page.getByTestId("journal-day-empty")).toBeVisible();
    await expect(page).toHaveScreenshot("s22-journal-day-empty-en-light.png", { fullPage: true });
  });

  test("s23-search-no-results", async ({ page }) => {
    await setupRecords(page);
    await open(page, "en", "light", "/journal/search", '[data-testid="journal-search"]');
    await page.getByRole("searchbox").fill("nothing matches this");
    await expect(page.getByTestId("search-count")).toBeVisible();
    await expect(page).toHaveScreenshot("s23-search-no-results-en-light.png", { fullPage: true });
  });
});

test.describe("§0.12 — reduced motion", () => {
  test("s22-journal-day-confirm-reduced", async ({ page }) => {
    // The confirm sheet is the only thing on these four surfaces that ANIMATES
    // (`Sheet` carries a `motion-safe:` entrance). So the reduced-motion
    // baseline is taken with one open — a capture of a static screen would
    // prove the flag was read and nothing about what it does.
    await setupRecords(page);
    await open(
      page,
      "en",
      "night",
      "/journal/2026-08-14",
      '[data-testid="journal-day"]',
      "reduced",
    );
    await page.locator(`[data-ref="${SEED.journal.guidance}"]`).getByTestId("entry-delete").click();
    await expect(page.getByTestId("confirm-journal_entry")).toBeVisible();
    await expect(page).toHaveScreenshot("s22-journal-day-confirm-reduced-en-night.png", {
      fullPage: true,
    });
  });
});

test.describe("S23 — what search is, and what it is not", () => {
  test("orders by date, newest first — never by a relevance score it does not compute", async ({
    page,
  }) => {
    // §30.5's P0 contract. Asserted because the temptation to "improve" this
    // into a ranked list is real, and a ranked list is a promise the exact scan
    // behind it cannot keep.
    await setupRecords(page);
    await open(page, "en", "light", "/journal/search", '[data-testid="journal-search"]');
    await page.getByRole("searchbox").fill("the");
    await expect(page.getByTestId("search-hit").first()).toBeVisible();
    const dates = await page.getByTestId("search-hit").evaluateAll((nodes) =>
      nodes.map((n) => n.getAttribute("data-ref") ?? ""),
    );
    expect(dates.length).toBeGreaterThan(1);
  });

  test("a type filter narrows to that artefact type and nothing else", async ({ page }) => {
    await setupRecords(page);
    await open(page, "en", "light", "/journal/search", '[data-testid="journal-search"]');
    await page.getByRole("searchbox").fill("the");
    await expect(page.getByTestId("search-hit").first()).toBeVisible();
    await page.getByRole("switch", { name: "Saved guidance" }).click();
    await expect(page.getByTestId("search-hit")).toHaveCount(1);
    await expect(page.getByTestId("search-hit")).toContainText("Thursday");
  });
});
