import { expect, test } from "@playwright/test";

import { SKIP_LAUNCH, serverState, setupApi } from "./_onboarding-fixtures";

/**
 * S02 — the first interactive screen, and the one the suite could not see.
 *
 * ── What was broken, and what the old tests were actually exercising ───────
 *
 * S02 called `PATCH /v1/onboarding`, which is behind `CurrentSession` in
 * `sitara_api.onboarding` (§33.2's product identity comes from the §34.5
 * cookie). But §29.1 orders onboarding **language (S02) → auth (S03)**, so at
 * this screen there is no session yet. In a real browser every language tap
 * returned 401, `useStepCommit` correctly refused to advance a step it could
 * not persist, and onboarding was sealed shut at its first screen. Same
 * language or different made no difference — there was nothing to authorise
 * the write.
 *
 * The flow suite stayed green because `stub-api.mjs` answered 200 to ANY caller:
 * it had no session gate at all. So the existing tests were exercising the
 * click handler, the locale switch and the route — against a server that
 * granted onboarding writes to anonymous users, which the real service never
 * does. They verified the parts either side of the authorisation and never the
 * authorisation itself. That is the root CLAUDE.md rule, broken in the fake:
 * "a fake that accepts what the real system rejects is a defect in the fake."
 *
 * The stub now refuses `/v1` without a session, and these tests run with NO
 * session — the state a real user is in on S02.
 */

const LOCALES = ["hi", "en", "hi-Latn"] as const;

/** The label each locale's own language row carries, in its own script. */
const OWN_LANGUAGE: Record<(typeof LOCALES)[number], string> = {
  hi: "हिन्दी",
  en: "English",
  "hi-Latn": "Hinglish",
};

/** S02 is step 2; S03 (auth) is where it must land. */
const LANGUAGE_STEP = 2;

test.describe("S02 — before there is a session", () => {
  for (const locale of LOCALES) {
    test(`${locale}: selecting the ALREADY-ACTIVE language advances to S03`, async ({ page }) => {
      // No session: this is the pre-auth world S02 actually runs in.
      const clientId = await setupApi(page, {
        locale,
        state: { session_user_id: null },
      });
      await page.goto(`/${locale}/start/language${SKIP_LAUNCH}`);

      // Confirming the language you are already in is a real answer, not a
      // no-op. Selecting and advancing are two different things.
      await page.getByText(OWN_LANGUAGE[locale], { exact: true }).click();

      await expect(page).toHaveURL(new RegExp(`/${locale}/start/auth$`));
      // The step is RECORDED even though it cannot yet be persisted — the
      // locale reaches the server at `POST /auth/session`, the first
      // authenticated moment in the stack.
      await expect(page.getByTestId("phone-input")).toBeVisible();

      // And nothing was written server-side, because nothing could be.
      const state = await serverState(clientId);
      expect(state.completed_steps).not.toContain(LANGUAGE_STEP);
    });

    test(`${locale}: switching to a DIFFERENT language also advances`, async ({ page }) => {
      const other = locale === "en" ? "hi" : "en";
      await setupApi(page, { locale, state: { session_user_id: null } });
      await page.goto(`/${locale}/start/language${SKIP_LAUNCH}`);

      await page.getByText(OWN_LANGUAGE[other], { exact: true }).click();

      // The locale switch and the advance happen in ONE navigation.
      await expect(page).toHaveURL(new RegExp(`/${other}/start/auth$`));
    });
  }

  test("no request is made at all — there is nothing to authorise yet", async ({ page }) => {
    await setupApi(page, { locale: "hi", state: { session_user_id: null } });
    await page.goto(`/hi/start/language${SKIP_LAUNCH}`);

    const calls: string[] = [];
    page.on("request", (r) => {
      if (r.url().includes("/v1/") || r.url().includes("/auth/")) {
        calls.push(`${r.method()} ${new URL(r.url()).pathname}`);
      }
    });

    await page.getByText("हिन्दी", { exact: true }).click();
    await expect(page).toHaveURL(/\/hi\/start\/auth$/);

    // The screen used to fire a PATCH that could only ever 401. A screen that
    // asks a question it has no right to ask, then refuses to move when it is
    // told no, is a dead end dressed as caution.
    expect(calls.filter((c) => c.includes("/v1/onboarding"))).toHaveLength(0);
  });

  test("the language choice survives to the session exchange (§34.5)", async ({ page }) => {
    // S02's answer is not lost by going unpersisted: next-intl pins it in the
    // URL and cookie, and `POST /auth/session` carries it to the server.
    const clientId = await setupApi(page, { locale: "en", state: { session_user_id: null } });
    await page.goto(`/en/start/language${SKIP_LAUNCH}`);

    await page.getByText("हिन्दी", { exact: true }).click();
    await expect(page).toHaveURL(/\/hi\/start\/auth$/);

    await page.getByTestId("phone-input").fill("8130225222");
    await page.getByTestId("phone-continue").click();
    await page.waitForURL(/\/hi\/start\/verify$/);
    await page.getByTestId("otp-input").fill("123456");
    await page.getByTestId("otp-verify").click();
    await page.waitForURL(/\/hi\/start\/consent$/);

    const state = await serverState(clientId);
    expect(state.session_user_id).not.toBeNull();
    expect(state.locale).toBe("hi");
  });
});
