import { expect, test, type Page } from "@playwright/test";

import { SEED, SKIP_LAUNCH, setupRecords } from "./_onboarding-fixtures";

/**
 * §24.8's screen baselines for M10's `/you` half — S25–S29.
 *
 * 5 surfaces × 3 locales × 2 themes = 30, plus the empty states, the
 * no-birth-details member and one reduced-motion capture of §45.3's sheet.
 * `journal-screens.spec.ts` carries S21–S24.
 *
 * The reasoning for the full locale × theme matrix is written out there and is
 * not repeated. Two things are specific to these five:
 *
 * **S28 is the first product surface that draws a kundli.** CC-007 shipped
 * `KundliChart`'s contract and an honest unbuilt state in M7 so §24.3's count of
 * 49 was true rather than aspirational; M10 drew it. A diagram is exactly the
 * kind of thing that renders plausibly and wrongly — the glyphs inside its boxes
 * are script-aware abbreviations, and a Devanagari baseline is the only gate
 * that can see a box whose label no longer fits it.
 *
 * **§45's memorial state has a baseline in both directions.** A member marked
 * `in_memory` must still look like a person in the list, not a disabled row, and
 * that is a judgement only a picture can settle.
 */

const LOCALES = ["en", "hi", "hi-Latn"] as const;
const THEMES = ["light", "night"] as const;

const SURFACES = [
  { id: "s29-you", path: "/you", ready: '[data-testid="you"]' },
  { id: "s25-vault", path: "/you/memories", ready: '[data-testid="vault"]' },
  {
    id: "s26-memory",
    path: `/you/memories/${SEED.memories.anniversary}`,
    ready: '[data-testid="memory"]',
  },
  { id: "s27-family", path: "/you/family", ready: '[data-testid="family"]' },
  {
    id: "s28-member",
    path: `/you/family/${SEED.family.mother}`,
    ready: '[data-testid="member"]',
  },
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

test.describe("§29.1 — S25–S29, the `/you` stack", () => {
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

test.describe("§24.6 — the `/you` designed empty states", () => {
  test("s25-vault-empty", async ({ page }) => {
    // §30.5: "Tara remembers only what you ask her to." An empty vault is the
    // correct state for a new account and the sentence says so — it is not a
    // gap to apologise for.
    await setupRecords(page, { scenario: "records_empty" });
    await open(page, "en", "light", "/you/memories", '[data-testid="vault"]');
    await expect(page).toHaveScreenshot("s25-vault-empty-en-light.png", { fullPage: true });
  });

  test("s27-family-empty", async ({ page }) => {
    await setupRecords(page, { scenario: "records_empty" });
    await open(page, "en", "light", "/you/family", '[data-testid="family"]');
    await expect(page).toHaveScreenshot("s27-family-empty-en-light.png", { fullPage: true });
  });

  test("s28-member-no-chart", async ({ page }) => {
    // §5.3: no birth details, no chart, and the engine declines rather than
    // guessing — so the screen states it in a sentence rather than rendering an
    // `ErrorState` with a retry control for something no retry can fix.
    await setupRecords(page);
    await open(page, "en", "light", `/you/family/${SEED.family.son}`, '[data-testid="member"]');
    await expect(page.getByTestId("member-chart-unavailable")).toBeVisible();
    await expect(page).toHaveScreenshot("s28-member-no-chart-en-light.png", { fullPage: true });
  });
});

test.describe("§45 — what 'in memory of' looks like", () => {
  test("s28-record-sheet · en · light", async ({ page }) => {
    // §45.3's sheet, both halves, in one picture. The non-destructive option is
    // above the destructive one and this is the artefact that shows it.
    await setupRecords(page);
    await open(page, "en", "light", `/you/family/${SEED.family.mother}`, '[data-testid="member"]');
    await page.getByTestId("member-record").click();
    await expect(page.getByTestId("family-record-sheet")).toBeVisible();
    await expect(page).toHaveScreenshot("s28-record-sheet-en-light.png", { fullPage: true });
  });

  test("s28-record-sheet · hi · night", async ({ page }) => {
    // Devanagari and the dusk theme together: the sheet is the densest text on
    // any M10 surface, and it is the one nobody may misread.
    await setupRecords(page, { locale: "hi" });
    await open(page, "hi", "night", `/you/family/${SEED.family.mother}`, '[data-testid="member"]');
    await page.getByTestId("member-record").click();
    await expect(page.getByTestId("family-record-sheet")).toBeVisible();
    await expect(page).toHaveScreenshot("s28-record-sheet-hi-night.png", { fullPage: true });
  });

  test("s27-family-in-memory", async ({ page }) => {
    // She stays in the list, marked. §45.2 is explicit that the member remains
    // in the family list, and §29.4 forbids carrying that state in colour or
    // opacity — a dimmed row is the visual language of "disabled" applied to a
    // person. Only a baseline can hold that line.
    await setupRecords(page);
    await open(page, "en", "light", `/you/family/${SEED.family.mother}`, '[data-testid="member"]');
    await page.getByTestId("member-record").click();
    await page.getByTestId("memorial-confirm").click();
    await expect(page.getByTestId("member-memorial")).toBeVisible();

    await open(page, "en", "light", "/you/family", '[data-testid="family"]');
    await expect(
      page.locator(`[data-member-id="${SEED.family.mother}"]`),
    ).toHaveAttribute("data-memorial", "in_memory");
    await expect(page).toHaveScreenshot("s27-family-in-memory-en-light.png", { fullPage: true });
  });
});

test.describe("§0.12 — reduced motion", () => {
  test("s28-record-sheet-reduced", async ({ page }) => {
    await setupRecords(page);
    await open(
      page,
      "en",
      "night",
      `/you/family/${SEED.family.mother}`,
      '[data-testid="member"]',
      "reduced",
    );
    await page.getByTestId("member-record").click();
    await expect(page.getByTestId("family-record-sheet")).toBeVisible();
    await expect(page).toHaveScreenshot("s28-record-sheet-reduced-en-night.png", {
      fullPage: true,
    });
  });
});
