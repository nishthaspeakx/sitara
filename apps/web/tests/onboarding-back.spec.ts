import { expect, test } from "@playwright/test";

import { SKIP_LAUNCH, setupApi } from "./_onboarding-fixtures";

/**
 * §28.1's navigation rules, applied to the onboarding stack.
 *
 *   "onboarding is a linear stack — back = previous step, exit-intent shows a
 *    save-progress note, never a blank page"
 *   "browser back closes topmost sheet/overlay before popping routes"
 *
 * Each of those has a failure mode that is invisible until someone presses
 * Back: a stack that pops history instead of walking steps lands OUTSIDE the
 * app when the user arrived by a resume redirect, and an overlay that ignores
 * Back makes the whole screen feel stuck.
 */

test.describe("§28.1 — the onboarding stack's back rules", () => {
  test("back walks to the previous STEP, not backwards through history", async ({ page }) => {
    await setupApi(page);

    // Arrive at S09 directly, as a resume redirect does. There is no history
    // entry for S08, so a stack that popped history would leave the app.
    await page.goto(`/en/start/interest${SKIP_LAUNCH}`);
    await expect(page.getByTestId("onboarding-stack")).toHaveAttribute("data-step", "9");

    await page.getByRole("button", { name: /back/i }).click();
    await page.waitForURL(/\/start\/city$/);
    await expect(page.getByTestId("onboarding-stack")).toHaveAttribute("data-step", "8");

    await page.getByRole("button", { name: /back/i }).click();
    await page.waitForURL(/\/start\/birth\/time$/);
  });

  test("back from the FIRST step shows the save-progress note, never a blank page", async ({
    page,
  }) => {
    await setupApi(page);
    await page.goto(`/en/start/language${SKIP_LAUNCH}`);

    await page.getByRole("button", { name: /back/i }).click();

    // §28.1's exit-intent note. §29.2 forbids what it could easily become:
    // no countdown, no guilt, and leaving is offered as plainly as staying.
    const note = page.getByTestId("exit-note");
    await expect(note).toBeVisible();
    await expect(note).not.toBeEmpty();
    await expect(page.getByRole("button", { name: /leave/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /keep going/i })).toBeVisible();

    // Whatever happens, the page underneath is still the screen — not blank.
    await expect(page.getByTestId("onboarding-stack")).toBeVisible();
  });

  test("browser back closes the topmost sheet before it pops the route", async ({ page }) => {
    await setupApi(page);
    await page.goto(`/en/start/birth${SKIP_LAUNCH}`);

    await page.getByRole("button", { name: /why we ask/i }).click();
    const sheet = page.getByRole("dialog");
    await expect(sheet).toBeVisible();

    await page.goBack();

    // The sheet closed and the ROUTE did not move. (The launch override
    // rides in the query string, so the path is what is asserted.)
    await expect(sheet).toBeHidden();
    expect(new URL(page.url()).pathname).toBe("/en/start/birth");
  });

  test("closing a sheet by its control leaves Back working in one press", async ({ page }) => {
    await setupApi(page);
    await page.goto(`/en/start/city${SKIP_LAUNCH}`);

    // Open and close the S43 explainer with its own control. The history entry
    // the overlay pushed must come back off, or the user's next Back would be
    // swallowed and the screen would feel stuck.
    await page.getByTestId("city-use-location").click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.getByRole("button", { name: /type it instead/i }).click();
    await expect(page.getByRole("dialog")).toBeHidden();

    await page.getByRole("button", { name: /back/i }).click();
    await page.waitForURL(/\/start\/birth\/time$/);
  });

  test("§24.4 — a resumed stack returns to the step it was left on", async ({ page }) => {
    // The server says S02–S08 are done, so S09 is where she left off.
    await setupApi(page, { state: { completed_steps: [2, 3, 4, 5, 6, 7, 8] } });

    await page.goto(`/en/${SKIP_LAUNCH}`);
    await page.waitForURL(/\/start\/interest$/);
    await expect(page.getByTestId("onboarding-stack")).toHaveAttribute("data-step", "9");
  });

  test("a finished stack skips onboarding entirely and lands on Today", async ({ page }) => {
    await setupApi(page, {
      state: { completed_steps: [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13] },
    });

    await page.goto(`/en/${SKIP_LAUNCH}`);
    await page.waitForURL(/\/en\/today$/);
    await expect(page.getByTestId("today")).toBeVisible();
  });
});
