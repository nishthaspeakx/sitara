import { expect, test, type Page } from "@playwright/test";

import { SKIP_LAUNCH, setupApi } from "./_onboarding-fixtures";

/**
 * **No onboarding step may swallow a failure.**
 *
 * The live bug this was written for: S02's primary control persisted the choice
 * AND switched locale, and it switched first. The locale switch replaces the
 * React tree, so when the PATCH came back 404 the error was set on a component
 * that no longer existed. A user tapped a language and *nothing happened* — no
 * error, no retry, no advance. A dead button.
 *
 * §34.4 gives every failure an envelope with a `message_key` and a `retryable`
 * flag, and §24.6 says the screen must render it "in-locale, warm, one retry
 * action". Neither is worth anything if the screen navigates away from its own
 * error first, so this is table-driven over EVERY step that writes: force the
 * write to fail, and assert the user is told and can try again.
 *
 * The requests travel the real path (browser → next start → middleware →
 * rewrite → stub-api), so a step whose URL is wrong fails here the same way it
 * fails in a browser.
 */

interface Step {
  id: string;
  route: string;
  /** Get the screen into a state where its primary control will submit. */
  arrange?: (page: Page) => Promise<void>;
  submit: (page: Page) => Promise<void>;
}

const STEPS: Step[] = [
  {
    id: "S02 language",
    route: "/start/language",
    submit: (page) => page.getByRole("button", { name: /English/ }).first().click(),
  },
  {
    id: "S05 consent",
    route: "/start/consent",
    submit: (page) => page.getByTestId("consent-continue").click(),
  },
  {
    id: "S07 birth-time",
    route: "/start/birth",
    arrange: async (page) => {
      await page.getByTestId("birth-date").fill("1994-03-17");
      await page.getByRole("searchbox").fill("Beng");
      await page.getByTestId("place-results").getByText("Bengaluru").click();
      await page.getByTestId("birth-continue").click();
      await page.waitForURL(/\/start\/birth\/time$/);
      await page.getByTestId("accuracy-exact").locator("input").check();
      await page.getByTestId("birth-time").fill("06:45");
    },
    submit: (page) => page.getByTestId("birth-time-continue").click(),
  },
  {
    id: "S08 city",
    route: "/start/city",
    arrange: async (page) => {
      await page.getByRole("searchbox").fill("Mum");
      await page.getByTestId("city-results").getByText("Mumbai").click();
    },
    submit: (page) => page.getByTestId("city-continue").click(),
  },
  {
    id: "S09 interest",
    route: "/start/interest",
    arrange: (page) => page.getByTestId("interest-balanced").click(),
    submit: (page) => page.getByTestId("interest-continue").click(),
  },
  {
    id: "S10 name",
    route: "/start/name",
    arrange: (page) => page.getByTestId("name-input").fill("Nishtha"),
    submit: (page) => page.getByTestId("name-continue").click(),
  },
  {
    id: "S11 priorities",
    route: "/start/priorities",
    arrange: (page) => page.getByTestId("priority-chips").getByRole("button").first().click(),
    submit: (page) => page.getByTestId("priorities-continue").click(),
  },
  {
    id: "S12 voice",
    route: "/start/voice",
    submit: (page) => page.getByTestId("voice-continue").click(),
  },
];

for (const step of STEPS) {
  test(`${step.id} surfaces a failed write and offers a retry`, async ({ page }) => {
    // S07's arrange walks through S06, which needs its own write to succeed —
    // so the failure is switched on after the screen is in position.
    const clientId = await setupApi(page, {
      state: { completed_steps: [2, 3, 4, 5, 6], has_birth_details: true },
    });
    await page.goto(`/en${step.route}${SKIP_LAUNCH}`);
    await step.arrange?.(page);

    await fetch("http://127.0.0.1:3101/__control/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        clientId,
        scenario: "fail_writes",
        state: { completed_steps: [2, 3, 4, 5, 6], has_birth_details: true },
      }),
    });

    const before = page.url();
    await step.submit(page);

    // 1 — the user is TOLD. In-locale copy, never a raw key, never silence.
    const alert = page.locator("main").getByRole("alert");
    await expect(alert, `${step.id} showed nothing at all`).toBeVisible({ timeout: 10_000 });
    await expect(alert).not.toBeEmpty();
    const text = await alert.innerText();
    expect(text).not.toMatch(/\b(errors|ui|start)\.[a-z0-9_]+\.[a-z0-9_.]+/);

    // 2 — §34.4's `retryable: true` means a retry control exists (§24.6's ONE).
    await expect(page.getByRole("button", { name: /retry|try again/i })).toHaveCount(1);

    // 3 — and it did NOT advance. A step that navigates on a failed write loses
    //     the answer silently, and resume would send the user back to it with
    //     no idea why.
    expect(new URL(page.url()).pathname, `${step.id} advanced despite failing`).toBe(
      new URL(before).pathname,
    );
  });
}

test("S03 surfaces a failed session exchange", async ({ page }) => {
  await setupApi(page, { scenario: "auth_fails" });
  await page.goto(`/en/start/auth${SKIP_LAUNCH}`);

  // The fake adapter mints a token; the exchange is what fails, which is the
  // half that talks to sitara-api and therefore the half a URL defect breaks.
  await page.getByTestId("phone-input").fill("8130225222");
  await page.getByTestId("phone-continue").click();
  await page.waitForURL(/\/start\/verify$/);
  await page.getByTestId("otp-input").fill("123456");
  await page.getByTestId("otp-verify").click();

  const alert = page.locator("main").getByRole("alert");
  await expect(alert).toBeVisible({ timeout: 10_000 });
  await expect(alert).not.toBeEmpty();
  expect(new URL(page.url()).pathname).toBe("/en/start/verify");
});

test("S13 does not advance when the final write fails", async ({ page }) => {
  // The step that used to advance regardless. `next_step` is the LOWEST
  // unrecorded step, so an unrecorded step 13 drops the user back into the
  // ceremony on every future launch — permanently, with nothing explaining why.
  const clientId = await setupApi(page, {
    state: { completed_steps: [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12], has_birth_details: true },
  });
  await page.goto(`/en/start/reading${SKIP_LAUNCH}`);
  await expect(page.getByTestId("reading-line").first()).toBeVisible();

  await fetch("http://127.0.0.1:3101/__control/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      clientId,
      scenario: "fail_writes",
      state: { completed_steps: [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12], has_birth_details: true },
    }),
  });

  await page.getByTestId("reading-continue").click();

  await expect(page.locator("main").getByRole("alert")).toBeVisible({ timeout: 10_000 });
  expect(new URL(page.url()).pathname, "advanced on a failed write").toBe("/en/start/reading");
  // …and the way forward is still there, so she is told rather than trapped.
  await expect(page.getByTestId("reading-continue")).toBeEnabled();
});
