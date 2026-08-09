import { expect, test, type Page, type Route } from "@playwright/test";

/**
 * S13 — the first-reading ceremony, and every way it is allowed to fail.
 *
 * This suite was written BEFORE the screen. It is the contract, not a
 * regression net, and it exists because S13 is the most consequential screen in
 * the product: §0.17 gates the whole covenant on ">=80% of onboarding completers
 * reach the minute-3 reading". A user who reaches it and sees a spinner that
 * never resolves has been failed at the exact moment the product is asking for
 * her trust.
 *
 * Two spec rules do the binding:
 *
 *   §24.6 — "no dead ends, no blame". Loading is a skeleton mirroring the final
 *     layout; error is in-locale, warm, ONE retry action; there is never a
 *     blank screen.
 *   §28.1 — onboarding "back = previous step, exit-intent shows a save-progress
 *     note, never a blank page". The stack must always be leavable FORWARD too:
 *     a ceremony the user cannot complete or escape is a trap.
 *
 * So every case below asserts the same four invariants, whatever went wrong:
 *
 *   1. no `aria-busy` element survives the deadline — the skeleton always
 *      resolves into something
 *   2. what replaces it is a real localised sentence or an honest ErrorState,
 *      never an empty region
 *   3. no raw i18n key leaks (§2.4 — a missing key is a defect, not a fallback)
 *   4. the user can always continue to Today
 *
 * The confidence state is asserted per case because §5.4's honesty is the
 * PRODUCT here: a reading built without a birth time must SAY it is
 * approximate, and one built without a chart must not claim otherwise.
 */

const READING_ROUTE = "**/v1/readings/first";
const ONBOARDING_ROUTE = "**/v1/onboarding";

/** Set on the flows webServer so the client deadline is testable in seconds. */
const DEADLINE_MS = Number(process.env.NEXT_PUBLIC_CEREMONY_DEADLINE_MS ?? 1500);

/**
 * A user who has completed S02–S12. S13 is reachable only from a complete
 * stack, so the resume guard needs this to let the ceremony mount at all.
 */
const COMPLETED_ONBOARDING = {
  locale: "en",
  completed_steps: [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
  birth_time_known: true,
  brief_time: "07:00",
};

/** §34.2 — the artefact embeds the snapshot it cited, so the stub carries one. */
const MOON_NAKSHATRA_FACT = {
  fact_id: "natal.graha.nakshatra:moon:v1",
  kind: "natal.graha.nakshatra",
  value: { graha: "moon", nakshatra: "rohini" },
  source: "sitara-astro",
  confidence: "verified",
};

const HOUSE_FACT = {
  fact_id: "natal.house_assignment:venus:v1",
  kind: "natal.house_assignment",
  value: { graha: "venus", whole_sign_house: 7 },
  source: "sitara-astro",
  confidence: "verified",
};

const PANCHANG_FACT = {
  fact_id: "panchang.tithi:2026-08-09:bengaluru",
  kind: "panchang.tithi",
  value: { tithi_index: 11, paksha: "shukla" },
  source: "divineapi",
  confidence: "verified",
};

const COMPLETE_READING = {
  status: "complete",
  confidence: "verified",
  source_state: "default",
  missing: [],
  degrade_reason: null,
  lines: [
    {
      id: "moon_nakshatra",
      values: { nakshatra: "Rohini" },
      fact_ids: [MOON_NAKSHATRA_FACT.fact_id],
      confidence: "verified",
    },
    {
      id: "observation",
      house: 7,
      values: { graha: "Venus" },
      fact_ids: [HOUSE_FACT.fact_id],
      confidence: "verified",
    },
    {
      id: "panchang",
      values: { tithi: "Ekadashi", paksha: "Shukla" },
      fact_ids: [PANCHANG_FACT.fact_id],
      confidence: "verified",
    },
  ],
  facts: [MOON_NAKSHATRA_FACT, HOUSE_FACT, PANCHANG_FACT],
};

async function stubOnboarding(page: Page) {
  await page.route(ONBOARDING_ROUTE, (route: Route) =>
    route.fulfill({ json: COMPLETED_ONBOARDING }),
  );
}

/** §34.4 envelope — the only error shape the client may ever receive. */
function envelope(code: string, messageKey: string, retryable: boolean) {
  return { code, message_key: messageKey, trace_id: "trace-ceremony-test", retryable };
}

/**
 * The four invariants. Asserted by every case so that a future degradation
 * path cannot be added without satisfying them.
 */
async function assertNeverStranded(page: Page) {
  // 1 — the skeleton resolved
  await expect(page.locator('[aria-busy="true"]')).toHaveCount(0);

  // 2 — something real is on screen: composed lines OR an honest error, and in
  //     either case not an empty box.
  //
  //     Scoped to `main`: Next mounts an always-present, always-empty
  //     `role="alert"` route announcer on every page, so an unscoped alert
  //     query matches a thing that is never the screen's error.
  const lines = page.getByTestId("reading-line");
  const error = page.locator("main").getByRole("alert");
  const lineCount = await lines.count();
  if (lineCount > 0) {
    for (let i = 0; i < lineCount; i += 1) {
      await expect(lines.nth(i)).not.toBeEmpty();
    }
  } else {
    await expect(error).toBeVisible();
    await expect(error).not.toBeEmpty();
  }

  // 3 — no raw key leaked. A key that failed to resolve renders as its own
  //     dotted path, which no localised sentence ever looks like.
  const body = (await page.locator("main").innerText()).trim();
  expect(body.length).toBeGreaterThan(0);
  expect(body).not.toMatch(/\b(start|launch|ui|errors)\.[a-z0-9_]+\.[a-z0-9_.]+/);

  // 4 — the way forward always exists and works
  const forward = page.getByTestId("reading-continue");
  await expect(forward).toBeVisible();
  await expect(forward).toBeEnabled();
}

test.describe("S13 first-reading ceremony — degradation", () => {
  test.beforeEach(async ({ page }) => {
    await stubOnboarding(page);
  });

  test("the engine answers slowly but within the deadline: the real reading arrives", async ({
    page,
  }) => {
    await page.route(READING_ROUTE, async (route: Route) => {
      await new Promise((r) => setTimeout(r, Math.floor(DEADLINE_MS * 0.5)));
      await route.fulfill({ json: COMPLETE_READING });
    });

    await page.goto("/en/start/reading");

    // The skeleton is what the user sees first — §24.6 forbids a spinner on a
    // content surface, so this must be the skeleton and not a throbber.
    // `aria-busy` rather than role=status: the brief-time Slider renders an
    // <output>, whose implicit role is status too.
    await expect(page.locator('[aria-busy="true"]')).toBeVisible();

    await expect(page.getByTestId("reading-line")).toHaveCount(3);
    await expect(page.getByTestId("reading-confidence")).toHaveAttribute("data-state", "verified");
    await expect(page.getByTestId("reading-degraded-note")).toHaveCount(0);
    await assertNeverStranded(page);
  });

  test("the request never resolves: the client deadline fires and the user is not stranded", async ({
    page,
  }) => {
    // Never fulfilled, never aborted — the hang that no server-side timeout can
    // rescue, and the exact failure this suite exists for.
    await page.route(READING_ROUTE, () => {});

    await page.goto("/en/start/reading");
    await expect(page.locator('[aria-busy="true"]')).toBeVisible();

    // Past the deadline the ceremony must have given up honestly.
    await page.waitForTimeout(DEADLINE_MS + 500);

    await expect(page.getByTestId("reading-degraded-note")).toBeVisible();
    await assertNeverStranded(page);

    // And the escape actually leaves.
    await page.getByTestId("reading-continue").click();
    await expect(page).toHaveURL(/\/en\/today$/);
  });

  test("no birth time: Moon-chart framing, an approximate chip, and the add-time affordance", async ({
    page,
  }) => {
    await page.route(READING_ROUTE, (route: Route) =>
      route.fulfill({
        json: {
          ...COMPLETE_READING,
          status: "partial",
          confidence: "approximate",
          missing: ["birth_time"],
          degrade_reason: "insufficient_birth_data",
          // §5.3: no lagna-sensitive claim survives a missing birth time, so
          // the house observation is absent rather than guessed.
          lines: COMPLETE_READING.lines.filter(
            (l) => l.id !== "observation",
          ),
          facts: [MOON_NAKSHATRA_FACT, PANCHANG_FACT],
        },
      }),
    );

    await page.goto("/en/start/reading");

    await expect(page.getByTestId("reading-confidence")).toHaveAttribute(
      "data-state",
      "approximate",
    );
    // §28.2's missing-birth-time variant: ASK, never nag and never guess.
    await expect(page.getByTestId("reading-add-birth-time")).toBeVisible();
    await assertNeverStranded(page);

    // The affordance goes back to the birth PAIR rather than dead-ending in a
    // note. S06 and not S07: the row is written whole through §13's facade, so
    // S07 without a date or place cannot submit and bounces — landing her on
    // the step that can actually finish is the point of the button.
    await page.getByTestId("reading-add-birth-time").click();
    await expect(page).toHaveURL(/\/en\/start\/birth$/);
  });

  test("the chart engine is down: a panchang-only reading, one retry, flow still advances", async ({
    page,
  }) => {
    let attempts = 0;
    await page.route(READING_ROUTE, (route: Route) => {
      attempts += 1;
      if (attempts === 1) {
        return route.fulfill({
          status: 503,
          json: envelope("ASTRO_ENGINE_UNAVAILABLE", "errors.astro.engine_unavailable", true),
        });
      }
      return route.fulfill({
        json: {
          ...COMPLETE_READING,
          status: "partial",
          confidence: "tradition_based_general",
          missing: ["natal_chart"],
          degrade_reason: "engine_unavailable",
          lines: COMPLETE_READING.lines.filter((l) => l.id === "panchang"),
          facts: [PANCHANG_FACT],
        },
      });
    });

    await page.goto("/en/start/reading");

    // §24.6: in-locale, warm, ONE retry action.
    const retry = page.getByRole("button", { name: /retry|try again/i });
    await expect(retry).toHaveCount(1);
    await assertNeverStranded(page);

    await retry.click();

    await expect(page.getByTestId("reading-line")).toHaveCount(1);
    await expect(page.getByTestId("reading-confidence")).toHaveAttribute(
      "data-state",
      "tradition_based_general",
    );
    await assertNeverStranded(page);
  });

  test("the panchang is unavailable but the chart is not: chart lines only, no invented timings", async ({
    page,
  }) => {
    await page.route(READING_ROUTE, (route: Route) =>
      route.fulfill({
        json: {
          ...COMPLETE_READING,
          status: "partial",
          confidence: "verified_limited_birth_data",
          missing: ["panchang"],
          degrade_reason: "panchang_unavailable",
          lines: COMPLETE_READING.lines.filter((l) => l.id !== "panchang"),
          facts: [MOON_NAKSHATRA_FACT, HOUSE_FACT],
        },
      }),
    );

    await page.goto("/en/start/reading");

    await expect(page.getByTestId("reading-line")).toHaveCount(2);
    await expect(page.getByTestId("reading-confidence")).toHaveAttribute(
      "data-state",
      "verified_limited_birth_data",
    );
    // §5.3 cite-or-die: with no panchang fact there is no panchang sentence and
    // no strip pretending to one.
    await expect(page.getByTestId("reading-panchang")).toHaveCount(0);
    await assertNeverStranded(page);
  });

  test("everything fails: an honest error with a retry AND a working way to Today", async ({
    page,
  }) => {
    await page.route(READING_ROUTE, (route: Route) =>
      route.fulfill({
        status: 503,
        json: envelope("SYS_UNAVAILABLE", "errors.sys.unavailable", true),
      }),
    );

    await page.goto("/en/start/reading");

    await expect(page.locator("main").getByRole("alert")).toBeVisible();
    await expect(page.getByRole("button", { name: /retry|try again/i })).toHaveCount(1);
    await assertNeverStranded(page);

    // §29.5 — Tara never appears on an error surface. The ceremony is the one
    // screen where the temptation to keep her on stage is strongest.
    //
    // Asserted through her CC-008 disclosure rather than a test id: the
    // "Tara · AI guide" label is mandatory wherever her face appears, so its
    // absence is the same fact as her absence, and it cannot be made vacuous by
    // someone removing a test hook.
    await expect(page.getByText("Tara · AI guide")).toHaveCount(0);

    await page.getByTestId("reading-continue").click();
    await expect(page).toHaveURL(/\/en\/today$/);
  });

  test("degradation is honest in every locale, not just English", async ({ page }) => {
    await page.route(READING_ROUTE, (route: Route) =>
      route.fulfill({
        status: 503,
        json: envelope("ASTRO_ENGINE_UNAVAILABLE", "errors.astro.engine_unavailable", true),
      }),
    );

    for (const locale of ["hi", "hi-Latn"] as const) {
      await page.route(ONBOARDING_ROUTE, (route: Route) =>
        route.fulfill({ json: { ...COMPLETED_ONBOARDING, locale } }),
      );
      await page.goto(`/${locale}/start/reading`);

      await assertNeverStranded(page);

      // §2.4 — no silent English fallback, ever. Devanagari must actually be
      // Devanagari; a catalog that fell back would read as Latin here.
      if (locale === "hi") {
        const text = await page.locator("main").innerText();
        expect(text).toMatch(/[ऀ-ॿ]/);
      }
    }
  });
});
