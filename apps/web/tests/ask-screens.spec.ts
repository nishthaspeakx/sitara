import { readFileSync } from "node:fs";
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

import en from "@sitara/i18n/messages/en.json" with { type: "json" };
import hi from "@sitara/i18n/messages/hi.json" with { type: "json" };
import hiLatn from "@sitara/i18n/messages/hi-Latn.json" with { type: "json" };

import {
  SKIP_LAUNCH,
  setupApi,
  setupSocket,
  type ChatFixture,
  type SocketBehaviour,
} from "./_onboarding-fixtures";

/**
 * §24.8's design-QA gate for S18 — §25.4's chat, in every launch locale, in
 * both themes.
 *
 * The component suite covers each component's states in isolation. A chat
 * screen is neither a component nor a sixteen-faced surface like Today: it is
 * one thread whose interesting failures are compositional and TEXTUAL —
 * a citation underline landing on the wrong words in Devanagari, a memory chip
 * pushing the composer off a 390px viewport, a Hinglish date pill wrapping, a
 * takeover that still shows a tab bar. None of that is visible in a story.
 *
 *   11 states × 3 locales × 2 themes   66   the matrix
 *   reduced motion, typing              1   §0.12's collapsed path — the dots
 *                                           are the one thing on this screen
 *                                           that loops
 *                                     ───
 *                                      67
 *
 * Every turn behind these is REAL pipeline output, recorded by
 * `services/api/scripts/record_chat_fixtures.py` and replayed over a REAL
 * WebSocket by `scripts/stub-realtime.mjs`. That matters more here than it does
 * for Today: a chat turn carries citation SPANS, and a hand-written span would
 * draw a plausible-looking underline over words no validator ever verified —
 * which is the single defect these baselines exist to catch.
 *
 * ── CL-013 ────────────────────────────────────────────────────────────────
 * No `page.route`, and no `window.WebSocket` replacement either.
 */

const LOCALES = ["en", "hi", "hi-Latn"] as const;
const THEMES = ["light", "night"] as const;

/** The eleven faces of S18. */
const STATES = [
  "empty",
  "thread",
  "cited",
  "trust_open",
  "typing",
  "memory_offer",
  "memory_accepted",
  "takeover",
  "failed",
  "handoff",
  "unavailable",
] as const;
type AskState = (typeof STATES)[number];

/** Which recorded turn and socket behaviour each state needs. */
const SETUP: Record<
  AskState,
  { turn?: ChatFixture; behaviour?: SocketBehaviour; scenario?: "chat_unavailable" }
> = {
  empty: {},
  thread: { turn: "claimless" },
  cited: { turn: "two_claims" },
  trust_open: { turn: "grounded" },
  typing: {},
  memory_offer: { turn: "memory_offer" },
  memory_accepted: { turn: "memory_offer" },
  takeover: { turn: "crisis" },
  failed: { behaviour: "drop_before_reply" },
  handoff: { behaviour: "handoff" },
  unavailable: { scenario: "chat_unavailable" },
};

/**
 * `ui.chat.retry`, per locale. A single English literal here would have made
 * `failed` and `unavailable` unreachable in hi and hi-Latn — the two locales
 * whose baselines are the reason this matrix has three columns.
 */
const CATALOGS: Record<string, { ui: { chat: { retry: string; open_trust: string } } }> = {
  en, hi, "hi-Latn": hiLatn,
};
const sendAgain = (locale: string) => CATALOGS[locale]!.ui.chat.retry;

/**
 * The accessible name a citation underline carries, per locale.
 *
 * `ui.chat.open_trust` is `Why Tara said "{text}"`, and its Hindi and Hinglish
 * forms share none of those words — a hard-coded /^Why Tara said/ found two
 * underlines in English and zero in the two locales this matrix exists to
 * check. The prefix is taken from the catalog and escaped, so the locator
 * follows the copy through the §14 language pass.
 */
function openTrust(locale: string): RegExp {
  const prefix = CATALOGS[locale]!.ui.chat.open_trust.split("{text}")[0]!;
  return new RegExp(prefix.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
}

async function settle(page: Page, theme: string) {
  // Re-applied after hydration replaces <html>'s attributes on a client nav.
  await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);
  await expect(page.locator('[aria-busy="true"]')).toHaveCount(0);
}

/**
 * A fixed wall clock, so a bubble's timestamp is not a baseline's expiry date.
 *
 * §25.4 puts the time INSIDE the bubble, and `MessageList.timeIn` formats
 * `message.at` — which is `Date.now()` at the moment the message was created.
 * Every message-bearing baseline here therefore encoded the minute it was
 * recorded in, and passed only while the clock happened to read the same
 * "10:29 AM". Outside that minute all thirty-six failed on a diff nobody had
 * changed anything to cause. Found while re-baselining for M9's mic button;
 * the mic is a real visual change and the timestamps were never one.
 *
 * `setFixedTime` freezes `Date.now()` without freezing timers, so the socket,
 * the reconnect backoff and the typing indicator all still run.
 */
const SHUTTER = new Date("2026-08-13T10:29:00Z");

async function open(page: Page, locale: string, theme: string) {
  await page.clock.setFixedTime(SHUTTER);
  await page.addInitScript((t) => {
    document.documentElement.setAttribute("data-theme", t as string);
  }, theme);
  await page.goto(`/${locale}/ask${SKIP_LAUNCH}`);
  await expect(page.getByTestId("ask").or(page.getByTestId("safety-takeover"))).toBeVisible();
  await settle(page, theme);
}

/**
 * Type a question — after the socket is live, unless told otherwise.
 *
 * **`page.goto` resolving is not the socket being open.** `ChatSocket.connect`
 * first POSTs `/v1/chat/session` for a ticket and only then upgrades, so there
 * is a window in which the screen is fully rendered and `send()` returns false.
 * The page then correctly falls back to `POST /v1/chat/turn` (§32.11's handoff
 * path) and the stub-api answers it — successfully. Which means a test meaning
 * to observe a socket DROP instead observed a perfectly good HTTP reply, and no
 * "Send again" button ever appeared.
 *
 * Idle this never happened; under four workers it did, intermittently, and only
 * ever in whichever locale lost the race that run. Waiting on the state the
 * product publishes (`data-connected`) is what makes these deterministic
 * — the same wait `ask-voice.spec.ts` does before a recording, for the same
 * reason.
 *
 * `awaitSocket: false` is for the scenarios where a socket is never expected:
 * `unavailable` 503s the session grant, so waiting for a connection that is
 * designed not to happen would hang until the timeout.
 */
async function ask(
  page: Page,
  text = "what is Saturn doing?",
  { awaitSocket = true }: { awaitSocket?: boolean } = {},
) {
  if (awaitSocket) {
    await expect(page.getByTestId("ask")).toHaveAttribute("data-connected", "true");
  }
  const field = page.getByTestId("composer").getByRole("textbox");
  await field.fill(text);
  await field.press("Enter");
}

/**
 * Drive the screen into one of the eleven states.
 *
 * Every one of these is reached the way a user reaches it — a real message over
 * a real socket, a real drop, a real 503. None is injected.
 */
async function reach(page: Page, state: AskState, locale: string) {
  switch (state) {
    case "empty":
      return;

    case "thread":
    case "cited":
      await ask(page);
      await expect(page.getByTestId("message-tara")).toBeVisible();
      return;

    case "trust_open": {
      await ask(page);
      const cited = page.getByTestId("message-tara").getByRole("button").first();
      await expect(cited).toBeVisible();
      await cited.click();
      await expect(page.getByRole("dialog")).toBeVisible();
      return;
    }

    case "typing": {
      // The socket is told to hold the turn: the indicator is the state under
      // capture, so it has to still be up when the shutter falls.
      await ask(page);
      await expect(page.getByTestId("typing-indicator")).toBeVisible();
      return;
    }

    case "memory_offer":
      await ask(page);
      await expect(page.getByTestId("memory-chip")).toBeVisible();
      return;

    case "memory_accepted": {
      await ask(page);
      const chip = page.getByTestId("memory-chip");
      await expect(chip).toBeVisible();
      await chip.getByRole("button").first().click();
      return;
    }

    case "takeover":
      await ask(page, "I want to kill myself");
      await expect(page.getByTestId("safety-takeover")).toBeVisible();
      return;

    case "failed":
      await ask(page);
      await expect(page.getByRole("button", { name: sendAgain(locale) })).toBeVisible({
        timeout: 15_000,
      });
      return;

    case "handoff":
      await expect(page.getByTestId("handoff-banner")).toBeVisible({ timeout: 15_000 });
      return;

    case "unavailable":
      // No socket here by design: the `chat_unavailable` scenario fails the
      // session grant, so the turn goes over HTTP and fails there too.
      await ask(page, "what is Saturn doing?", { awaitSocket: false });
      await expect(page.getByRole("button", { name: sendAgain(locale) })).toBeVisible({
        timeout: 15_000,
      });
      return;
  }
}

test.describe("§24.8 — S18 baselines", () => {
  for (const state of STATES) {
    for (const locale of LOCALES) {
      for (const theme of THEMES) {
        test(`${state} · ${locale} · ${theme}`, async ({ page }) => {
          const setup = SETUP[state];
          const client = await setupApi(page, {
            locale,
            chatTurn: setup.turn ?? "grounded",
            scenario: setup.scenario,
          });
          await setupSocket(client, {
            turn: setup.turn ?? "grounded",
            locale,
            // The typing state needs the indicator still UP when the shutter
            // falls, so the socket emits its presence events and then holds.
            // `drop_before_reply` cannot serve it: a close correctly clears the
            // indicator, which is the behaviour the socket spec asserts.
            behaviour: state === "typing" ? "hold" : setup.behaviour,
            stages:
              state === "typing"
                ? ["safety_pre", "memory_retrieval"]
                : ["safety_pre", "memory_retrieval", "generation"],
          });

          await open(page, locale, theme);
          await reach(page, state, locale);

          // §25.4's permanent disclosure (CC-008) is on every face of this
          // screen that shows her name — checked on every capture rather than
          // once, because the takeover is the one that must NOT show her.
          if (state === "takeover") {
            await expect(page.getByTestId("safety-takeover").locator("img")).toHaveCount(0);
          } else {
            await expect(page.getByTestId("ask-header")).toContainText("AI");
          }

          await expect(page).toHaveScreenshot(`ask-${state}-${locale}-${theme}.png`, {
            fullPage: false,
          });
        });
      }
    }
  }
});

test("§0.12 — the typing indicator under reduced motion", async ({ page }) => {
  /**
   * The one looping thing on this screen. Under `data-motion="reduced"` the
   * dots must not animate — the token layer collapses every duration, and the
   * `motion-off:` variant covers the forced path the harness uses.
   */
  const client = await setupApi(page, { locale: "en" });
  await setupSocket(client, {
    behaviour: "hold",
    stages: ["safety_pre", "memory_retrieval"],
  });
  await page.addInitScript(() => {
    document.documentElement.setAttribute("data-motion", "reduced");
  });
  await open(page, "en", "light");
  await page.evaluate(() => document.documentElement.setAttribute("data-motion", "reduced"));
  await ask(page);
  await expect(page.getByTestId("typing-indicator")).toBeVisible();

  await expect(page).toHaveScreenshot("ask-typing-reduced-motion.png", { fullPage: false });
});

test.describe("§25.4 — the honesty layer survives every locale", () => {
  /**
   * Not a baseline: a per-locale assertion that the underline covers the words
   * the SERVER verified. A picture proves the underline is there; only this
   * proves it is in the right place, and Devanagari is where an offset bug in
   * code points vs UTF-16 units would first show.
   */
  for (const locale of LOCALES) {
    test(`the cited span is the server's span · ${locale}`, async ({ page }) => {
      const client = await setupApi(page, { locale, chatTurn: "two_claims" });
      await setupSocket(client, { turn: "two_claims", locale });
      await open(page, locale, "light");
      await ask(page);

      // Scoped to the citation underlines: the message wrapper also carries a
      // screen-reader-only "actions" button, which is not an underline.
      const underlines = page
        .getByTestId("message-tara")
        .getByRole("button", { name: openTrust(locale) });
      await expect(underlines).toHaveCount(2);

      // The rendered underline must be the SERVED slice, character for
      // character. `contentParts` splits on code points; a UTF-16 slice would
      // come back short for anything outside the BMP, and Devanagari is where
      // that shows first.
      const served = JSON.parse(
        readFileSync(
          path.join(__dirname, "__fixtures__", "chat", `two_claims.${locale}.json`),
          "utf-8",
        ),
      ) as { text: string; citations: Array<{ span_start: number; span_end: number }> };
      const expected = served.citations.map((c) =>
        [...served.text].slice(c.span_start, c.span_end).join(""),
      );

      expect((await underlines.allInnerTexts()).map((t) => t.trim())).toEqual(expected);
    });
  }
});
