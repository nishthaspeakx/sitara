import { expect, test, type Page } from "@playwright/test";

import en from "@sitara/i18n/messages/en.json" with { type: "json" };
import hi from "@sitara/i18n/messages/hi.json" with { type: "json" };
import hiLatn from "@sitara/i18n/messages/hi-Latn.json" with { type: "json" };

import {
  SKIP_LAUNCH,
  setupApi,
  setupSocket,
  type SocketBehaviour,
} from "./_onboarding-fixtures";

/**
 * §24.8's design-QA gate for S19 — §25.3's call screen, every state, every
 * launch locale, both themes.
 *
 *   7 live states  × en only     × 2 themes = 14
 *   3 refusals     × the locales that can reach them = 16
 *                                                    ───
 *                                                     30
 *
 * ── Why the LIVE matrix is English only, and why that is not a gap ────────
 *
 * CC-010: `hi` and `hi-Latn` have no streaming recogniser, so `POST
 * /v1/call/session` REFUSES those locales and the live screen is unreachable
 * in them. Baselining it anyway would have meant making the stub grant a call
 * the real API declines — a fake that accepts what the real system rejects,
 * which is the root CLAUDE.md rule and the one the onboarding stub broke.
 *
 * So the three locales are covered on the screen they can actually reach: the
 * refusal. `test_the_live_matrix_widens_when_cc_010_lifts` below fails the day
 * a Hindi grant starts succeeding, which is the commit that should also widen
 * this matrix — the same self-unblocking discipline `call_gate._indic_blocked`
 * follows on the server.
 *
 * Per-locale cover for the call CONTROLS is not missing meanwhile:
 * `CallControls` is a library component and the component suite already runs
 * it through 4 locales × 2 themes, plan chip and privacy line included.
 *
 * ── Why this surface needs them more than most ────────────────────────────
 *
 * The call is the only full-bleed screen in the product. Everything on it is
 * light text over a photographic background, which is the one composition where
 * §29.4's "state is never colour alone" and §24.2's contrast floors are decided
 * by the IMAGE rather than by a token pair — and no component story can show
 * that, because in a story the portrait is not behind anything.
 *
 * Three specific regressions these exist to catch, none of which fails a
 * typecheck, a lint or a behavioural test:
 *
 *   · the 25% scrim drifting (§25.3 fixes the dim; §29.4 forbids filtering her
 *     instead), which makes the timer unreadable on the lighter frames;
 *   · the §32.9 notice or the plan chip wrapping in hi/hi-Latn — Devanagari is
 *     taller and Hinglish longer, and both sit in a fixed-height control row;
 *   · the handoff panel losing the portrait's dim behind it, which is where the
 *     one solid-background surface on the screen sits.
 *
 * ── Determinism ───────────────────────────────────────────────────────────
 *
 * Two things move on this screen and both are pinned:
 *
 *   · **the timer.** `setFixedTime` freezes `Date.now()` without freezing
 *     timers, so the socket, its backoff and the screen's own 1s interval all
 *     still run while the clock reads one value. The two warning states advance
 *     the clock deliberately — a "5 minutes left" notice over a 0:00 timer is a
 *     frame that could never happen, and it is also the only way to see the
 *     wider `MM:SS` glyph run.
 *   · **the state machine.** Each state is driven to a stub behaviour that
 *     STOPS there. `connecting` is the one that needed a new one (`hold_ready`):
 *     it is real, it is brief, and racing the handshake would have captured it
 *     about once in twenty runs.
 *
 * No `page.route`, and no `window.WebSocket` replacement (CL-013). The browser
 * performs a real upgrade against `scripts/stub-realtime.mjs`.
 */

const LOCALES = ["en", "hi", "hi-Latn"] as const;
const THEMES = ["light", "night"] as const;

/** The locales a live call can be granted in today (CC-010). */
const LIVE_LOCALES = ["en"] as const;

/** §25.3's states, plus the two the controls own. */
const STATES = [
  "connecting",
  "listening",
  "speaking",
  "muted",
  "warning_5",
  "warning_2",
  "handoff",
] as const;
type CallState = (typeof STATES)[number];

const CATALOGS: Record<string, typeof en> = { en, hi, "hi-Latn": hiLatn };

const SHUTTER = new Date("2026-08-13T10:29:00Z");
/** 2:07 into the call — a two-digit seconds run the 0:00 frames never show. */
const ELAPSED_MS = 127_000;

async function open(page: Page, locale: string, theme: string) {
  await page.clock.setFixedTime(SHUTTER);
  await page.addInitScript((t) => {
    document.documentElement.setAttribute("data-theme", t as string);
  }, theme);
  await page.goto(`/${locale}/ask/call${SKIP_LAUNCH}`);
  await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);
  await expect(page.locator('[aria-busy="true"]')).toHaveCount(0);
}

/**
 * Drive the screen into one state and wait for the thing that proves it.
 *
 * Every wait is on a state the PRODUCT publishes — `data-call-state`, a
 * testid, a catalog string — never on a timeout. A `waitForTimeout` here would
 * make the flakiest baselines the ones for the states that take longest to
 * arrive, which is exactly backwards.
 */
async function drive(page: Page, state: CallState, locale: string): Promise<void> {
  const t = CATALOGS[locale]!;

  switch (state) {
    case "connecting":
      // The socket upgraded and `session.ready` never came.
      await expect(page.locator('[data-call-state="connecting"]')).toBeVisible();
      return;

    case "listening":
      await expect(page.locator('[data-call-state="listening"]')).toBeVisible();
      return;

    case "speaking":
      await expect(page.locator('[data-call-state="speaking"]')).toBeVisible();
      await expect(page.getByTestId("call-captions")).toBeVisible();
      return;

    case "muted":
      await expect(page.locator('[data-call-state="speaking"]')).toBeVisible();
      await page.getByRole("button", { name: t.ui.call.mute }).click();
      // The control reports its own state; §29.4 wants that in the a11y tree
      // and not only in the icon.
      await expect(page.getByRole("button", { name: t.ui.call.unmute })).toHaveAttribute(
        "aria-pressed",
        "true",
      );
      return;

    case "warning_5":
    case "warning_2": {
      // Wait on the NOTICE, not on a call state. §32.9's warning arrives while
      // she is finishing an utterance, so by the time it is on screen the state
      // has already moved back to `listening` — an earlier version waited for
      // `speaking` and timed out on a screen that was showing exactly what the
      // baseline wanted.
      const notice = page.getByRole("button", { name: /\d/ }).first();
      await expect(notice).toBeVisible();
      // A "minutes left" notice over a 0:00 timer is a frame that could never
      // happen. Advancing the fixed clock keeps determinism and makes the
      // baseline show a call that has actually been running.
      await page.clock.setFixedTime(new Date(SHUTTER.getTime() + ELAPSED_MS));
      await expect(page.getByTestId("call-timer")).toHaveText("2:07");
      return;
    }

    case "handoff":
      await expect(page.getByTestId("call-handoff")).toBeVisible();
      await expect(page.getByText(t.ui.call.handoff_title)).toBeVisible();
      return;
  }
}

/** Which socket behaviour (and grant) each state needs. */
const SETUP: Record<CallState, { behaviour: SocketBehaviour; warningMinutes?: number }> = {
  connecting: { behaviour: "hold_ready" },
  listening: { behaviour: "connecting" },
  speaking: { behaviour: "speaking" },
  muted: { behaviour: "speaking" },
  warning_5: { behaviour: "warning", warningMinutes: 5 },
  warning_2: { behaviour: "warning", warningMinutes: 2 },
  handoff: { behaviour: "tts_kill" },
};

test.describe("§25.3 — the live call screen", () => {
  for (const state of STATES) {
    for (const locale of LIVE_LOCALES) {
      for (const theme of THEMES) {
        test(`${state} · ${locale} · ${theme}`, async ({ page }) => {
          const client = await setupApi(page, { locale });
          const setup = SETUP[state];
          await setupSocket(client, {
            behaviour: setup.behaviour,
            locale,
            warningMinutes: setup.warningMinutes,
          });
          await open(page, locale, theme);
          await drive(page, state, locale);
          await expect(page).toHaveScreenshot(`s19-call-${state}-${locale}-${theme}.png`, {
            fullPage: true,
          });
        });
      }
    }
  }
});

test.describe("§25.3 — the screen each locale can actually reach", () => {
  /**
   * Every reason a call is refused, on the locales that can reach it.
   *
   * These are the hi/hi-Latn baselines. They are not a consolation prize for
   * the live matrix being English: a Hindi speaker tapping the call button
   * today gets this screen and nothing else, so this IS their call screen, and
   * §24.8's per-locale gate belongs on it.
   */
  const REFUSALS = [
    { id: "refused-disabled", scenario: "calls_disabled" as const, locales: LOCALES },
    { id: "refused-exhausted", scenario: "call_minutes_exhausted" as const, locales: LOCALES },
    // Only reachable where CC-010 bites. Asking for it in `en` would render
    // nothing, and a baseline of nothing passes forever.
    { id: "refused-language", scenario: "ok" as const, locales: ["hi", "hi-Latn"] as const },
  ];

  for (const refusal of REFUSALS) {
    for (const locale of refusal.locales) {
      for (const theme of THEMES) {
        test(`${refusal.id} · ${locale} · ${theme}`, async ({ page }) => {
          const client = await setupApi(page, { locale, scenario: refusal.scenario });
          await setupSocket(client, { behaviour: "hold_ready", locale });
          await open(page, locale, theme);
          await expect(page.getByRole("alert").first()).toBeVisible();
          await expect(page.locator('[data-call-state]')).toHaveCount(0);
          await expect(page).toHaveScreenshot(`s19-call-${refusal.id}-${locale}-${theme}.png`, {
            fullPage: true,
          });
        });
      }
    }
  }
});

test.describe("what the baselines are there to hold", () => {
  test("the live matrix widens when CC-010 lifts, and fails until it is widened", async ({
    page,
  }) => {
    // A guard on the matrix above, not on the product. The day a Hindi call
    // grant succeeds, this fails and points at `LIVE_LOCALES` — so the matrix
    // widens on the commit that makes it possible rather than months later
    // when somebody notices the screen has never been seen in Devanagari.
    const client = await setupApi(page, { locale: "hi" });
    await setupSocket(client, { behaviour: "hold_ready", locale: "hi" });
    await open(page, "hi", "light");

    await expect(page.getByRole("alert").first()).toBeVisible();
    expect(LIVE_LOCALES).toEqual(["en"]);
  });

  test("the scrim sits over the portrait and is not a filter on her", async ({ page }) => {
    // §29.4: never cropped through the face, never flipped, never filtered
    // beyond the graded masters. A `filter`/`opacity` on the image would look
    // identical to a scrim in a screenshot at one dim value and diverge at
    // every other — so this is asserted in the DOM, not left to the picture.
    const client = await setupApi(page);
    await setupSocket(client, { behaviour: "speaking" });
    await open(page, "en", "light");

    const portrait = page.locator("main img").first();
    const filters = await portrait.evaluate((el) => {
      const style = getComputedStyle(el);
      return { filter: style.filter, opacity: style.opacity };
    });
    expect(filters.filter === "none" || filters.filter === "").toBe(true);
    expect(Number(filters.opacity)).toBe(1);
  });

  test("§25.3's 25% dim is really applied, at 25%", async ({ page }) => {
    // **A pixel diff cannot hold this one, and that is the finding.**
    // `maxDiffPixelRatio` is 0.001 — very tight on HOW MANY pixels may move —
    // but Playwright's per-pixel `threshold` is its default 0.2 in YIQ space.
    // A uniform 25% navy overlay shifts every pixel by less than that, so the
    // whole dim can vanish and all 14 live-call baselines still pass. Verified
    // by cranking it to 95%, which does move them, and back.
    //
    // So the screenshots would NOT have caught the missing scrim either — a
    // human looking at the image did. This assertion is the mechanical guard:
    // it reads the computed colour, where 25% is exactly 25% and an absent
    // rule is `rgba(0, 0, 0, 0)`.
    const client = await setupApi(page);
    await setupSocket(client, { behaviour: "speaking" });
    await open(page, "en", "light");

    const scrim = page.locator('main > div[aria-hidden="true"].inset-0').first();
    const background = await scrim.evaluate((el) => getComputedStyle(el).backgroundColor);
    // rgba(15, 19, 48, 0.25) — brand-navy-deep at §25.3's dim.
    expect(background).toMatch(/^rgba\(15,\s*19,\s*48,\s*0?\.25\)$/);
  });

  test("the disclosure is on the call screen wherever the call screen is", async ({ page }) => {
    // CC-008 / §25.2 — permanent wherever her name or face appears, and the
    // full-bleed portrait is the largest place her face appears anywhere.
    // Asserted on the locales that can reach it; §29.5 keeps her OFF the
    // refusal screen entirely, which is why the others are not checked here.
    for (const locale of LIVE_LOCALES) {
      const client = await setupApi(page, { locale });
      await setupSocket(client, { behaviour: "connecting", locale });
      await open(page, locale, "light");
      await expect(page.getByText(CATALOGS[locale]!.ui.tara.ai_label)).toBeVisible();
    }
  });

  test("she is never the face of a refused call (§29.5)", async ({ page }) => {
    // §29.5: no Tara on error surfaces. A refusal is an error surface, and the
    // call screen is the one place a full-bleed portrait would otherwise be
    // sitting behind it.
    const client = await setupApi(page, { scenario: "calls_disabled" });
    await setupSocket(client, { behaviour: "hold_ready" });
    await open(page, "en", "light");

    await expect(page.getByRole("alert").first()).toBeVisible();
    await expect(page.locator('img[src*="/tara/"]')).toHaveCount(0);
  });

  test("the timer is tabular, so a rising second does not reflow the row", async ({ page }) => {
    const client = await setupApi(page);
    await setupSocket(client, { behaviour: "speaking" });
    await open(page, "en", "light");

    const variant = await page
      .getByTestId("call-timer")
      .evaluate((el) => getComputedStyle(el).fontVariantNumeric);
    expect(variant).toContain("tabular-nums");
  });
});
