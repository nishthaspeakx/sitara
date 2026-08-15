import { expect, test, type Page } from "@playwright/test";

import { SKIP_LAUNCH, setupApi } from "./_onboarding-fixtures";

/**
 * §24.8's screen baselines for M11's payment surfaces — S30, S31 and S34.
 *
 * The full locale × theme matrix, for the reason `you-screens.spec.ts` gives
 * and one more that is specific to money:
 *
 * **§2.3 gives INR Indian digit grouping and USD Western grouping, and `Intl`
 * groups by LOCALE rather than by currency.** So a `hi` reader looking at a
 * USD price — an NRI gift, a subscriber who moved abroad, both cases §30.3
 * ships with — is exactly where the obvious implementation renders
 * `$14,50,000`. That is a defect no typecheck, lint or behavioural test can
 * see, and a picture settles it. `sub_international` exists for that one
 * assertion.
 *
 * **CC-013's Latin numerals are checked the same way.** Every price and every
 * §22.13 date on these screens is a numeral in a Devanagari page, and the
 * failure mode is a `-u-nu-deva` extension somebody adds helpfully.
 *
 * ── The §22.13 states are the reason for most of these captures ────────────
 *
 * `grace` and `read_only` are BOTH failed renewals and say different things —
 * one keeps everything, one keeps her memories — and §29.2 forbids the
 * countdown-and-guilt register that most products reach for here. Whether the
 * copy reads as reassurance rather than as a chase is a judgement only a
 * picture can settle, in the language it will actually be read in.
 */

const LOCALES = ["en", "hi", "hi-Latn"] as const;
const THEMES = ["light", "night"] as const;

/** The three §29.1 screens, at the state each is most itself in. */
const SURFACES = [
  {
    id: "s30-subscription",
    path: "/you/subscription",
    ready: '[data-testid="subscription"]',
    scenario: "sub_grace",
  },
  {
    id: "s31-paywall",
    path: "/you/subscription/checkout",
    ready: '[data-testid="checkout"]',
    scenario: "sub_none",
  },
  {
    id: "s34-result",
    path: "/you/subscription/result?state=success",
    ready: '[data-testid="payresult"]',
    scenario: "sub_active",
  },
] as const;

async function open(
  page: Page,
  locale: string,
  theme: string,
  path: string,
  ready: string,
): Promise<void> {
  await page.addInitScript(
    ({ t }) => document.documentElement.setAttribute("data-theme", t as string),
    { t: theme },
  );
  // `SKIP_LAUNCH` is `?launch=static`; S34 already carries its own query, so
  // the separator is chosen rather than concatenated blindly.
  const join = path.includes("?") ? "&" : "?";
  await page.goto(`/${locale}${path}${join}${SKIP_LAUNCH.slice(1)}`);
  await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);
  await page.locator(ready).first().waitFor({ state: "visible" });
  await expect(page.locator('[aria-busy="true"]')).toHaveCount(0);
}

test.describe("§29.1 — S30, S31, S34", () => {
  for (const surface of SURFACES) {
    for (const locale of LOCALES) {
      for (const theme of THEMES) {
        test(`${surface.id} · ${locale} · ${theme}`, async ({ page }) => {
          await setupApi(page, { locale, scenario: surface.scenario });
          await open(page, locale, theme, surface.path, surface.ready);
          await expect(page).toHaveScreenshot(`${surface.id}-${locale}-${theme}.png`, {
            fullPage: true,
          });
        });
      }
    }
  }
});

test.describe("§22.13 — the dunning ladder, state by state", () => {
  // Each of these is a promise made in copy, and §29.2 rules out the register
  // most products use here. Captured in `hi` as well as `en` because "nothing
  // has changed" has to land as reassurance in the language it is read in, and
  // a translation that drifts into a chase is invisible to every other gate.
  const STATES = [
    { scenario: "sub_trialing", id: "s30-trialing" },
    { scenario: "sub_read_only", id: "s30-read-only" },
    { scenario: "sub_downgraded", id: "s30-downgraded" },
    { scenario: "sub_cancelled", id: "s30-cancelled" },
    { scenario: "sub_mandate", id: "s30-mandate" },
  ] as const;

  for (const state of STATES) {
    for (const locale of ["en", "hi"] as const) {
      test(`${state.id} · ${locale}`, async ({ page }) => {
        await setupApi(page, { locale, scenario: state.scenario });
        await open(page, locale, "light", "/you/subscription", '[data-testid="subscription"]');
        await expect(page).toHaveScreenshot(`${state.id}-${locale}-light.png`, {
          fullPage: true,
        });
      });
    }
  }

  test("read-only says her memories are safe and offers a way back", async ({ page }) => {
    // The behavioural half of the same promise: §22.13's read-only state is
    // not a lockout screen, so it carries a retry — and the copy that says
    // nothing is deleted has to be READ from the DOM, not assumed from a
    // picture that could have rendered a different key.
    await setupApi(page, { scenario: "sub_read_only" });
    await open(page, "en", "light", "/you/subscription", '[data-testid="subscription"]');
    const block = page.getByTestId("subscription-read-only");
    await expect(block).toBeVisible();
    await expect(block).toContainText("memories are safe");
    await expect(block.getByRole("button")).toBeVisible();
  });

  test("a downgraded account still says nothing was deleted", async ({ page }) => {
    await setupApi(page, { scenario: "sub_downgraded" });
    await open(page, "en", "light", "/you/subscription", '[data-testid="subscription"]');
    await expect(page.getByTestId("subscription-downgraded")).toContainText("nothing has been");
  });
});

test.describe("§2.3 — the currency rules, which only a picture can settle", () => {
  test("s30-international · hi · light", async ({ page }) => {
    // The whole reason this capture exists: §2.3 puts WESTERN grouping on USD,
    // `Intl` groups by locale, and this is a USD price on a Devanagari page.
    // A regression here renders `$14,50,000` and fails nothing else.
    await setupApi(page, { locale: "hi", scenario: "sub_international" });
    await open(page, "hi", "light", "/you/subscription", '[data-testid="subscription"]');
    await expect(page.getByTestId("subscription-summary")).toContainText("$99");
    await expect(page).toHaveScreenshot("s30-international-hi-light.png", { fullPage: true });
  });

  test("prices render in Latin numerals in hi (CC-013)", async ({ page }) => {
    // §46 fixes Latin digits in every locale including `hi`, and the thing to
    // preserve is the ABSENCE of a `-u-nu-deva` extension. A helpful addition
    // would render ₹३,९९९ and pass every other check.
    await setupApi(page, { locale: "hi", scenario: "sub_none" });
    await open(page, "hi", "light", "/you/subscription/checkout", '[data-testid="checkout"]');
    const body = await page.locator("body").innerText();
    expect(body).toContain("₹3,999");
    expect(body).not.toMatch(/[०-९]/);
  });

  test("the annual saving is stated plainly and never as zero", async ({ page }) => {
    // §29.1: "savings stated plainly". §29.2: nothing manufactured. ₹499 × 12
    // − ₹3,999 = ₹1,989, and `annualSaving` returns null rather than a "save
    // ₹0" chip when there is nothing to say.
    await setupApi(page, { scenario: "sub_none" });
    await open(page, "en", "light", "/you/subscription/checkout", '[data-testid="checkout"]');
    await expect(page.locator("body")).toContainText("₹1,989");
  });
});

test.describe("§29.2 — the dark-pattern checklist, on the screen itself", () => {
  test("S31 has no countdown, no guilt copy, and a close control", async ({ page }) => {
    await setupApi(page, { scenario: "sub_none" });
    await open(page, "en", "light", "/you/subscription/checkout", '[data-testid="checkout"]');

    // Close is always available — `Sheet` renders it unconditionally, and this
    // asserts the screen did not somehow suppress it.
    await expect(page.getByRole("button", { name: /close/i })).toBeVisible();

    // §30.3's acceptance: the total incl. tax is shown BEFORE the rail. It is a
    // required `PriceCard` prop, so this checks it reached the screen.
    await expect(page.locator("body")).toContainText("tax included");

    // No countdown can exist — `PriceCard` has no prop for one — but a screen
    // could still have added a timer of its own beside it.
    const body = await page.locator("body").innerText();
    expect(body).not.toMatch(/\d+:\d{2}\s*(left|remaining)/i);
    expect(body).not.toMatch(/hurry|last chance|only today|don't miss/i);
  });

  test("cancelling is one screen with no retention labyrinth", async ({ page }) => {
    // §30.3: "one screen, immediate confirm, access till period end stated, no
    // retention labyrinth — one optional 'tell us why'". The sheet states the
    // date, offers exactly two choices, and asks nothing before confirming.
    await setupApi(page, { scenario: "sub_active" });
    await open(page, "en", "light", "/you/subscription", '[data-testid="subscription"]');
    await page.getByTestId("subscription-cancel").click();

    const sheet = page.getByTestId("subscription-cancel-sheet");
    await expect(sheet).toContainText("keep everything until");
    await expect(sheet).toContainText("nothing is deleted");
    // Two controls plus the sheet's own close. No third "wait, here's an
    // offer" step, and no required field standing in front of the confirm.
    await expect(sheet.getByRole("button", { name: /yes, cancel/i })).toBeEnabled();
    await expect(sheet.locator("input, textarea")).toHaveCount(0);
    await expect(page).toHaveScreenshot("s30-cancel-sheet-en-light.png", { fullPage: true });
  });
});

test.describe("§30.3 — S34's three states", () => {
  for (const state of ["success", "pending", "failed"] as const) {
    test(`s34-${state} · en · light`, async ({ page }) => {
      await setupApi(page, { scenario: state === "success" ? "sub_active" : `pay_${state}` });
      await open(
        page,
        "en",
        "light",
        `/you/subscription/result?state=${state}${state === "failed" ? "&reason=insufficient_funds" : ""}`,
        '[data-testid="payresult"]',
      );
      await expect(page).toHaveScreenshot(`s34-${state}-en-light.png`, { fullPage: true });
    });
  }

  test("pending is NOT drawn as an error", async ({ page }) => {
    // §30.3's UPI hold is neither success nor failure, and the screen must not
    // borrow an error's language for it. Asserted as an absence, because the
    // way this regresses is somebody reusing the failure block.
    await setupApi(page, { scenario: "pay_pending" });
    await open(
      page,
      "en",
      "light",
      "/you/subscription/result?state=pending",
      '[data-testid="payresult"]',
    );
    await expect(page.getByTestId("payresult-pending")).toBeVisible();
    await expect(page.getByTestId("payresult-failed")).toHaveCount(0);
    await expect(page.locator("body")).toContainText("Approve in your UPI app");
    // §30.3's 5-minute hold, from the schema constant rather than a literal.
    await expect(page.locator("body")).toContainText("5 minutes");
  });

  test("a failure states the mapped reason and offers one retry", async ({ page }) => {
    // §30.3: "mapped reasons in plain language … + one retry CTA + alternate-
    // rail suggestion". The reason is a KEY the server chose; no vendor string
    // can reach this screen.
    await setupApi(page, { scenario: "pay_failed" });
    await open(
      page,
      "en",
      "light",
      "/you/subscription/result?state=failed&reason=insufficient_funds",
      '[data-testid="payresult"]',
    );
    await expect(page.locator("body")).toContainText("wasn't enough in the account");
    await expect(page.getByRole("button", { name: /try again/i })).toBeVisible();
  });

  test("an unmapped reason says the outcome without inventing a cause", async ({ page }) => {
    // `unknown` is a real member of §30.3's reason set. A screen that guessed
    // would be inventing a fact about somebody's bank account — §5.3's rule
    // pointed at money.
    await setupApi(page, { scenario: "pay_failed" });
    await open(
      page,
      "en",
      "light",
      "/you/subscription/result?state=failed&reason=something_a_rail_made_up",
      '[data-testid="payresult"]',
    );
    await expect(page.locator("body")).toContainText("didn't say why");
  });
});

test.describe("§30.3 — the gap, said plainly", () => {
  test("a region with no rail offers no purchase control at all", async ({ page }) => {
    // `payments.live_rails` is open: neither Razorpay nor Stripe is
    // implemented. Where no rail serves a region there is NO CONTROL rather
    // than a disabled one — `ErrorState`'s `retryable: false` rule applied to
    // an affordance, because a greyed button still asserts it is nearly there.
    await setupApi(page, { scenario: "sub_unavailable" });
    await open(page, "en", "light", "/you/subscription", '[data-testid="subscription"]');
    await expect(page.getByTestId("subscription-unavailable")).toBeVisible();
    await expect(page.getByTestId("subscription-none").getByRole("button")).toHaveCount(0);
    await expect(page).toHaveScreenshot("s30-unavailable-en-light.png", { fullPage: true });
  });

  test("every subscription screen discloses that no money moves", async ({ page }) => {
    // The prototype's own disclosure, and the same instinct as CC-008's
    // permanent "Tara · AI guide": where a thing is not what it appears to be,
    // the screen says so. A demo whose receipts look real is a demo somebody
    // eventually shows a customer.
    await setupApi(page, { scenario: "sub_active" });
    await open(page, "en", "light", "/you/subscription", '[data-testid="subscription"]');
    await expect(page.getByTestId("subscription-simulated")).toBeVisible();
  });
});
