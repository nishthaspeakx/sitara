import { expect, test, type Page } from "@playwright/test";

import { SKIP_LAUNCH, stubBackend } from "./_onboarding-fixtures";

/**
 * The complete §24.4 happy path, S01 → S13 → Today, in every launch locale.
 *
 * Run per locale rather than once, because §2.4's "no silent English fallback,
 * ever" is not a property of the catalogs — `i18n-lint` already proves those
 * agree — it is a property of the SCREENS. A key a screen never asks for cannot
 * be missing, and a key it asks for in the wrong namespace renders as a raw
 * dotted path. Only walking the flow in Devanagari finds that.
 *
 * The Hindi assertions are the sharpest: `data-script="devanagari"` has to be
 * on `<html>` (without it the §24.2 per-script size factor, leading and Noto
 * family never apply, and the page renders in whatever the device happens to
 * have), and the visible text has to actually be Devanagari.
 */

const LOCALES = ["en", "hi", "hi-Latn"] as const;

/** Locale → the script the §24.2 typography block keys off. */
const SCRIPT: Record<string, string> = {
  en: "latin",
  "hi-Latn": "latin",
  hi: "devanagari",
};

/** No screen may show a raw key — that is what a missing string looks like. */
async function assertNoRawKeys(page: Page) {
  const text = await page.locator("body").innerText();
  expect(text).not.toMatch(/\b(start|launch|ui|errors|auth|verify|dob)\.[a-z0-9_]+\.[a-z0-9_.]+/);
}

async function walkTheStack(page: Page, locale: string) {
  await stubBackend(page, locale);

  // ── S01 launch ──────────────────────────────────────────────────────────
  await page.goto(`/${locale}/${SKIP_LAUNCH}`);
  await expect(page.locator("html")).toHaveAttribute("data-script", SCRIPT[locale]!);
  await expect(page.getByTestId("launch-sequence")).toBeVisible();

  // ── S02 language ────────────────────────────────────────────────────────
  await page.waitForURL(new RegExp(`/${locale}/start/language$`));
  await assertNoRawKeys(page);
  // The eight cards are each written in their OWN script (§10-3), so the
  // Devanagari name is present whatever the active locale is.
  await expect(page.getByText("हिन्दी")).toBeVisible();
  await page.getByRole("button", { name: /English/ }).first().click();

  // ── S03 sign-up ─────────────────────────────────────────────────────────
  await page.waitForURL(/\/start\/auth$/);
  await assertNoRawKeys(page);
  await page.getByTestId("phone-input").fill("8130225222");
  await page.getByTestId("phone-continue").click();

  // ── S04 OTP ─────────────────────────────────────────────────────────────
  await page.waitForURL(/\/start\/verify$/);
  await assertNoRawKeys(page);
  await page.getByTestId("otp-input").fill("123456");
  await page.getByTestId("otp-verify").click();

  // ── S05 consent ─────────────────────────────────────────────────────────
  await page.waitForURL(/\/start\/consent$/);
  await assertNoRawKeys(page);
  await page.getByTestId("consent-continue").click();

  // ── S06 birth details ───────────────────────────────────────────────────
  await page.waitForURL(/\/start\/birth$/);
  await assertNoRawKeys(page);
  await page.getByTestId("birth-date").fill("1994-03-17");
  await page.getByRole("searchbox").fill("Beng");
  await page.getByTestId("place-results").getByText("Bengaluru").click();
  await page.getByTestId("birth-continue").click();

  // ── S07 time accuracy ───────────────────────────────────────────────────
  await page.waitForURL(/\/start\/birth\/time$/);
  await assertNoRawKeys(page);
  await page.getByTestId("accuracy-exact").locator("input").check();
  await page.getByTestId("birth-time").fill("06:45");
  await expect(page.getByTestId("accuracy-preview")).toBeVisible();
  await page.getByTestId("birth-time-continue").click();

  // ── S08 current city ────────────────────────────────────────────────────
  await page.waitForURL(/\/start\/city$/);
  await assertNoRawKeys(page);
  await page.getByRole("searchbox").fill("Mum");
  await page.getByTestId("city-results").getByText("Mumbai").click();
  await page.getByTestId("city-continue").click();

  // ── S09 interest ────────────────────────────────────────────────────────
  await page.waitForURL(/\/start\/interest$/);
  await assertNoRawKeys(page);
  await page.getByTestId("interest-balanced").click();
  await page.getByTestId("interest-continue").click();

  // ── S10 name ────────────────────────────────────────────────────────────
  await page.waitForURL(/\/start\/name$/);
  await assertNoRawKeys(page);
  await page.getByTestId("name-input").fill("Nishtha");
  await page.getByTestId("name-continue").click();

  // ── S11 priorities ──────────────────────────────────────────────────────
  await page.waitForURL(/\/start\/priorities$/);
  await assertNoRawKeys(page);
  const chips = page.getByTestId("priority-chips").getByRole("button");
  await chips.nth(0).click();
  await chips.nth(1).click();
  await page.getByTestId("priorities-continue").click();

  // ── S12 voice ───────────────────────────────────────────────────────────
  await page.waitForURL(/\/start\/voice$/);
  await assertNoRawKeys(page);
  await page.getByTestId("voice-continue").click();

  // ── S13 the ceremony ────────────────────────────────────────────────────
  await page.waitForURL(/\/start\/reading$/);
  await expect(page.getByTestId("reading-line")).toHaveCount(3);
  await assertNoRawKeys(page);
  await page.getByTestId("reading-continue").click();

  await page.waitForURL(new RegExp(`/${locale}/today$`));
  await assertNoRawKeys(page);
}

for (const locale of LOCALES) {
  test(`the whole onboarding stack completes in ${locale}`, async ({ page }) => {
    await walkTheStack(page, locale);
  });
}

test("Hindi renders in Devanagari, not in a silent English fallback", async ({ page }) => {
  await stubBackend(page, "hi");
  await page.goto(`/hi/start/consent${SKIP_LAUNCH}`);

  await expect(page.locator("html")).toHaveAttribute("data-script", "devanagari");
  const text = await page.locator("main").innerText();
  // §2.4: a fallback would render this screen in Latin. Devanagari or nothing.
  expect(text).toMatch(/[ऀ-ॿ]/);
  await assertNoRawKeys(page);
});

test("S11 enforces §24.4's three-priority cap in the interface, not just on the server", async ({
  page,
}) => {
  await stubBackend(page);
  await page.goto(`/en/start/priorities${SKIP_LAUNCH}`);

  const chips = page.getByTestId("priority-chips").getByRole("button");
  for (let i = 0; i < 3; i += 1) await chips.nth(i).click();

  // §24.6: an unresponsive control with no reason is a small dead end. The
  // unchosen chips disable rather than silently swallowing a tap.
  await expect(chips.nth(3)).toBeDisabled();
  await expect(chips.nth(0)).toBeEnabled();
});

test("§30.1 — the location prompt is unreachable without its explainer", async ({ page }) => {
  await stubBackend(page);
  let geolocationAsked = false;
  await page.addInitScript(() => {
    // Record any call rather than granting: the assertion is about ORDER.
    const original = navigator.geolocation?.getCurrentPosition;
    if (original) {
      Object.defineProperty(navigator.geolocation, "getCurrentPosition", {
        value: (...args: unknown[]) => {
          (window as unknown as { __geoAsked: boolean }).__geoAsked = true;
          return (original as (...a: unknown[]) => void).apply(navigator.geolocation, args);
        },
      });
    }
  });
  await page.goto(`/en/start/city${SKIP_LAUNCH}`);

  await page.getByTestId("city-use-location").click();
  geolocationAsked = await page.evaluate(
    () => (window as unknown as { __geoAsked?: boolean }).__geoAsked === true,
  );
  // §30.1: "No system permission dialog ever fires without its explainer sheet
  // shown first." Tapping the control opens the explainer and nothing else.
  expect(geolocationAsked).toBe(false);
  await expect(page.getByTestId("location-allow")).toBeVisible();

  // …and the no-permission path is on the screen the whole time (§30.1's
  // "manual entry equally prominent" and its feature-without-permission parity).
  await page.getByRole("button", { name: /type it instead/i }).click();
  await expect(page.getByRole("searchbox")).toBeVisible();
});
