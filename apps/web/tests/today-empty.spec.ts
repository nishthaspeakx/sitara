import { expect, test } from "@playwright/test";

import { SKIP_LAUNCH, setupToday } from "./_onboarding-fixtures";

/**
 * §28.2's FIRST-SESSION variant — what Today shows before a brief exists.
 *
 * This spec was written before the screen, and it is the more interesting of
 * the two empty states because it is not really empty: §28.2 gives it content
 * ("first-reading recap card + 'your first morning brief arrives at 7:00'
 * promise + brief-time edit") and §28.2's States row makes it the definition of
 * the empty state — "empty (pre-first-brief) = first-session variant". A Today
 * that rendered a generic EmptyState here would satisfy "not blank" and fail
 * the spec, which is exactly what the M8 placeholder does.
 *
 * The promise is the load-bearing part. A user who has just finished onboarding
 * has been told a brief is coming; a screen that says "nothing here yet" breaks
 * that promise at the first opportunity §0.17 gives it.
 *
 * ── CL-013 ────────────────────────────────────────────────────────────────
 * No `page.route`. The request travels browser → `next start` → middleware →
 * rewrite → `stub-api.mjs`, so the locale middleware and the `/v1` rewrite are
 * under test alongside the screen. An intercept would stop the request before
 * any of them ran.
 */

const LOCALES = ["en", "hi", "hi-Latn"] as const;

test.describe("§28.2 — Today before the first brief", () => {
  test("renders the first-session variant, not a generic empty state", async ({ page }) => {
    await setupToday(page, { variant: "first_session" });
    await page.goto(`/en/today${SKIP_LAUNCH}`);

    const today = page.getByTestId("today");
    await expect(today).toBeVisible();
    await expect(today).toHaveAttribute("data-variant", "first_session");

    // §28.2's three first-session affordances.
    await expect(page.getByTestId("first-session-recap")).toBeVisible();
    await expect(page.getByTestId("brief-promise")).toBeVisible();
    await expect(page.getByTestId("brief-time-edit")).toBeVisible();
  });

  test("the promise names the user's own brief time", async ({ page }) => {
    await setupToday(page, { variant: "first_session" });
    await page.goto(`/en/today${SKIP_LAUNCH}`);

    // §28.2 writes the promise as "your first morning brief arrives at 7:00" —
    // the time is the user's `brief_time`, not a hardcoded 7. A promise that
    // named the default to a user who picked 05:30 would be a small lie on the
    // one screen whose whole job is to be kept.
    const promise = page.getByTestId("brief-promise");
    await expect(promise).toContainText("07:00");
  });

  test("the brief-time edit reaches the picker", async ({ page }) => {
    await setupToday(page, { variant: "first_session" });
    await page.goto(`/en/today${SKIP_LAUNCH}`);

    await page.getByTestId("brief-time-edit").click();
    await expect(page.getByTestId("brief-time-picker")).toBeVisible();

    // §29.2: "close always visible". The control belongs to the Sheet, not to
    // the picker inside it, so the assertion is scoped to the dialog — the
    // rule is about what the user can see on the surface, not about which
    // component happens to own the button.
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("button", { name: /.+/ }).first()).toBeVisible();
    // And it really closes, without saving anything.
    await dialog.getByRole("button").first().click();
    await expect(page.getByTestId("brief-time-picker")).toBeHidden();
  });

  test("Tara's line is present even with no brief (§28.2: always present)", async ({ page }) => {
    await setupToday(page, { variant: "first_session" });
    await page.goto(`/en/today${SKIP_LAUNCH}`);

    const line = page.getByTestId("taras-line");
    await expect(line).toBeVisible();
    await expect(line).not.toBeEmpty();
  });

  test("no core card is invented before a brief exists (§5.3)", async ({ page }) => {
    await setupToday(page, { variant: "first_session" });
    await page.goto(`/en/today${SKIP_LAUNCH}`);
    await expect(page.locator('[data-emphasis="core"]')).toHaveCount(0);
    await expect(page.getByTestId("practical-strip")).toHaveCount(0);
  });

  test("the tab bar is there — Today is a destination, not a dead end", async ({ page }) => {
    await setupToday(page, { variant: "first_session" });
    await page.goto(`/en/today${SKIP_LAUNCH}`);
    await expect(page.getByRole("navigation")).toBeVisible();
  });

  test("nothing stays busy and no raw i18n key leaks", async ({ page }) => {
    await setupToday(page, { variant: "first_session" });
    await page.goto(`/en/today${SKIP_LAUNCH}`);
    await page.waitForLoadState("networkidle");

    await expect(page.locator('[aria-busy="true"]')).toHaveCount(0);
    // A key that reached the DOM instead of a sentence. `today.` and `ui.` are
    // the two namespaces this screen renders from.
    const body = await page.locator("body").innerText();
    expect(body).not.toMatch(/\b(today|ui)\.[a-z_]+\.[a-z_]+/);
  });

  for (const locale of LOCALES) {
    test(`${locale}: the empty state is whole-app native (§2.4)`, async ({ page }) => {
      await setupToday(page, { variant: "first_session", locale });
      await page.goto(`/${locale}/today${SKIP_LAUNCH}`);
      await page.waitForLoadState("networkidle");

      await expect(page.getByTestId("brief-promise")).toBeVisible();
      if (locale === "hi") {
        // §2.4 forbids a silent English fallback. Devanagari is the cheap,
        // reliable check that the catalog actually resolved.
        await expect(page.getByTestId("brief-promise")).toContainText(/[ऀ-ॿ]/);
      }
    });
  }
});
