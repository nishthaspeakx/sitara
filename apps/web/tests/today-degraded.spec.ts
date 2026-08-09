import { expect, test } from "@playwright/test";

import { SKIP_LAUNCH, setupToday } from "./_onboarding-fixtures";

/**
 * §28.2's PROVIDER-DEGRADED variant — what Today shows when the brief generated
 * but only reached §7.1's "verified core cards (panchang + one chart theme, no
 * LLM)".
 *
 * Two failures are possible here and they pull in opposite directions, which is
 * why this spec asserts both edges:
 *
 *   · **Saying too little.** §28.2 requires an honest line — "Tara has the
 *     essentials today; the full reading returns shortly" — not a silent short
 *     screen. A degraded brief that merely renders fewer cards is
 *     indistinguishable from a quiet morning, and the user is never told the
 *     reading they are owed is still coming.
 *
 *   · **Saying too much.** The degrade is narrower than LOW density on purpose
 *     (`ranking.core_cards` is deliberately not `rank(…, Density.LOW)`), so any
 *     contextual card on this screen is a card with no fact behind it. That is
 *     §5.3's failure mode, and the one the whole citation machinery exists to
 *     make impossible.
 *
 * And a third, quieter rule: §34.7 is explicit that a degraded state is not an
 * ALARM. `tradition_based_general` is a neutral fill; if this screen ever
 * reaches for caution or danger colour to say "something went wrong", it has
 * turned an honest limit into fear-selling (§9, §13).
 *
 * ── CL-013 ────────────────────────────────────────────────────────────────
 * No `page.route`. The recorded payload is served by a real process through the
 * real request path.
 */

const LOCALES = ["en", "hi", "hi-Latn"] as const;

test.describe("§28.2 — Today on verified core cards", () => {
  test("renders the degraded variant and says so honestly", async ({ page }) => {
    await setupToday(page, { variant: "provider_degraded" });
    await page.goto(`/en/today${SKIP_LAUNCH}`);

    const today = page.getByTestId("today");
    await expect(today).toHaveAttribute("data-variant", "provider_degraded");

    const note = page.getByTestId("degraded-note");
    await expect(note).toBeVisible();
    await expect(note).not.toBeEmpty();
  });

  test("the core card still exists and is still the only dominant one", async ({ page }) => {
    await setupToday(page, { variant: "provider_degraded" });
    await page.goto(`/en/today${SKIP_LAUNCH}`);

    // §28.2's acceptance rule holds in ALL variants: "core card visually
    // dominant in ALL variants". Degrading is not an exemption.
    await expect(page.locator('[data-emphasis="core"]')).toHaveCount(1);
  });

  test("no contextual card appears — the degrade is narrower than LOW", async ({ page }) => {
    await setupToday(page, { variant: "provider_degraded" });
    await page.goto(`/en/today${SKIP_LAUNCH}`);
    await page.waitForLoadState("networkidle");

    await expect(page.getByTestId("contextual-cards")).toHaveCount(0);

    // Whatever DID render must be one of the three `ranking.core_cards` emits.
    const rendered = await page.locator("[data-module]").evaluateAll((nodes) =>
      nodes.map((n) => n.getAttribute("data-module")),
    );
    expect(rendered.length).toBeGreaterThan(0);
    for (const id of rendered) {
      expect(["moon_nakshatra_note", "energy_of_day", "personal_chart_theme"]).toContain(id);
    }
  });

  test("the confidence chip is tradition_based_general and is not alarming", async ({ page }) => {
    await setupToday(page, { variant: "provider_degraded" });
    await page.goto(`/en/today${SKIP_LAUNCH}`);

    const chip = page.getByTestId("today-confidence");
    await expect(chip).toBeVisible();
    await expect(chip).toHaveAttribute("data-state", "tradition_based_general");

    // §34.7: "neither using caution/danger colours". Read the computed values
    // rather than the class list — a token could be re-aliased underneath.
    const caution = ["#B26A00", "#A56200", "#D08A3C"];
    const danger = ["#B3261E", "#C4564C", "#CD7169", "#B4453B"];
    const colours = await chip.evaluate((el) => {
      const s = getComputedStyle(el);
      return [s.color, s.backgroundColor, s.borderColor];
    });
    const hex = (rgb: string) => {
      const m = rgb.match(/\d+/g);
      if (!m) return "";
      return `#${m.slice(0, 3).map((v) => Number(v).toString(16).padStart(2, "0")).join("")}`.toUpperCase();
    };
    for (const value of colours) {
      expect([...caution, ...danger]).not.toContain(hex(value));
    }
  });

  test("every rendered claim is still one tap from a Trust Sheet (§30.4)", async ({ page }) => {
    await setupToday(page, { variant: "provider_degraded" });
    await page.goto(`/en/today${SKIP_LAUNCH}`);

    const cards = page.locator("[data-module]");
    const count = await cards.count();
    for (let i = 0; i < count; i += 1) {
      await expect(cards.nth(i).getByTestId("why-this")).toBeVisible();
    }

    await cards.first().getByTestId("why-this").click();
    const sheet = page.getByRole("dialog");
    await expect(sheet).toBeVisible();
    // §30.4: "fact-IDs remain internal (logs/admin) and never render to users".
    await expect(sheet).not.toContainText("[[fact:");
    await expect(sheet).not.toContainText(/\bnatal\.|panchang\.\w+:/);
  });

  test("the practical strip is absent — its facts were not in hand", async ({ page }) => {
    await setupToday(page, { variant: "provider_degraded" });
    await page.goto(`/en/today${SKIP_LAUNCH}`);
    // colour · number · favourable · caution are none of `core_cards`' three.
    await expect(page.getByTestId("practical-strip")).toHaveCount(0);
  });

  for (const locale of LOCALES) {
    test(`${locale}: the honest line is in the user's language (§2.4)`, async ({ page }) => {
      await setupToday(page, { variant: "provider_degraded", locale });
      await page.goto(`/${locale}/today${SKIP_LAUNCH}`);
      await page.waitForLoadState("networkidle");

      const note = page.getByTestId("degraded-note");
      await expect(note).toBeVisible();
      if (locale === "hi") await expect(note).toContainText(/[ऀ-ॿ]/);
      await expect(page.locator('[aria-busy="true"]')).toHaveCount(0);
    });
  }
});
