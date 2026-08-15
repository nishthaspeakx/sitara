import { expect, test, type Page } from "@playwright/test";

import en from "@sitara/i18n/messages/en.json" with { type: "json" };
import hi from "@sitara/i18n/messages/hi.json" with { type: "json" };

import { SKIP_LAUNCH, setupApi, setupSocket } from "./_onboarding-fixtures";

/**
 * §25.3's screen 17, over a REAL WebSocket.
 *
 * The socket rule from S18 applies with more force here, not less. Playwright
 * cannot intercept a WebSocket, so the only browser-side alternative would be
 * replacing `window.WebSocket` — and a call is the one surface where the things
 * that would then be unobservable are the whole feature: the handshake, the
 * ordering of her caption against her audio, the close, and the handoff. So the
 * browser performs a real upgrade against `scripts/stub-realtime.mjs`, whose
 * turns are RECORDED from the real §9 pipeline.
 *
 * **The chaos scenario is the reason this file exists.** `tts_kill` sends the
 * same frames `services/realtime` sends when synthesis dies mid-utterance, and
 * asserts what a person would see: her answer still on the screen, the audio
 * stopped, and a way into the thread that already holds every word.
 */

const CALL = `/en/ask/call${SKIP_LAUNCH}`;

const HANDOFF = en.ui.call.handoff_title;
const LISTENING = en.ui.call.listening;
const SPEAKING = en.ui.call.speaking;

async function open(page: Page, path = CALL) {
  await page.goto(path);
}

test.describe("§25.3 — the reference layout", () => {
  test("the screen carries the timer, the three controls and the disclosure", async ({
    page,
  }) => {
    const client = await setupApi(page);
    await setupSocket(client, { behaviour: "connecting" });
    await open(page);

    await expect(page.getByTestId("call-timer")).toBeVisible();
    // §25.3's three controls, "exactly as the reference".
    await expect(page.getByRole("button", { name: en.ui.call.mute })).toBeVisible();
    await expect(page.getByRole("button", { name: en.ui.call.end })).toBeVisible();
    await expect(page.getByRole("button", { name: en.ui.call.speaker_off })).toBeVisible();
    // CC-008 / §25.2 — permanent wherever her name or face appears.
    await expect(page.getByText(en.ui.tara.ai_label)).toBeVisible();
  });

  test("the privacy shield says something true and never claims E2E", async ({ page }) => {
    const client = await setupApi(page);
    await setupSocket(client, { behaviour: "connecting" });
    await open(page);

    await page.getByRole("button", { name: en.ui.call.privacy_title }).click();
    const body = page.getByText(en.ui.call.privacy_body);
    await expect(body).toBeVisible();
    // §13/§25.3: honest, and explicitly NOT an end-to-end claim.
    expect(en.ui.call.privacy_body).toContain("never recorded");
    expect(en.ui.call.privacy_body).toContain("not end-to-end encrypted");
  });

  test("live captions are on for a first call and show both sides", async ({ page }) => {
    const client = await setupApi(page);
    await setupSocket(client, { behaviour: "reply" });
    await open(page);

    const captions = page.getByTestId("call-captions");
    await expect(captions).toBeVisible();
    // The user's own speech, and then hers. A partial of TARA's words is
    // unrepresentable (§34.6) — `data-role=tara` is never `data-partial`.
    await expect(captions.locator('[data-role="user"]')).toContainText("Saturn");
    await expect(captions.locator('[data-role="tara"]')).toBeVisible();
    await expect(captions.locator('[data-role="tara"][data-partial]')).toHaveCount(0);
  });

  test("a returning caller's captions stay off", async ({ page }) => {
    // §25.3 asks for captions on the FIRST call. The server decides, from the
    // minutes already spent — a client-side memory would reset with storage.
    const client = await setupApi(page, { scenario: "call_returning" });
    await setupSocket(client, { behaviour: "connecting" });
    await open(page);

    await expect(page.getByTestId("call-captions")).toHaveCount(0);
  });
});

test.describe("§25.3's call states", () => {
  test("she is speaking while she is speaking", async ({ page }) => {
    // The scenario STOPS mid-utterance. An earlier version used `reply`, which
    // reaches `tts.end` in the same tick — so the screen was correct, the
    // assertion was chasing a state that had already passed, and the fix was
    // to make the state last rather than to loosen the assertion.
    const client = await setupApi(page);
    await setupSocket(client, { behaviour: "speaking" });
    await open(page);

    // Announced in words, never by the portrait alone (§29.4).
    await expect(page.getByText(SPEAKING)).toBeVisible();
    await expect(page.locator('[data-call-state="speaking"]')).toBeVisible();
  });

  test("a finished utterance returns her to listening", async ({ page }) => {
    const client = await setupApi(page);
    await setupSocket(client, { behaviour: "reply" });
    await open(page);

    await expect(page.locator('[data-call-state="listening"]')).toBeVisible();
  });

  test("the connecting state never claims to be connected", async ({ page }) => {
    const client = await setupApi(page);
    await setupSocket(client, { behaviour: "connecting" });
    await open(page);

    await expect(page.getByText(LISTENING)).toBeVisible();
  });
});

test.describe("the degrade ladder, over a real socket", () => {
  test("killing TTS mid-call lands in a text handoff with the words intact", async ({
    page,
  }) => {
    // The milestone's chaos path, frame for frame as `services/realtime` sends
    // it. `services/realtime/tests/test_call_degrade.py` asserts the same
    // sequence against the real service — the two would have to drift together
    // for both to be wrong.
    const client = await setupApi(page);
    await setupSocket(client, { behaviour: "tts_kill" });
    await open(page);

    const handoff = page.getByTestId("call-handoff");
    await expect(handoff).toBeVisible();
    await expect(handoff).toContainText(HANDOFF);
    await expect(handoff).toContainText(en.ui.call.handoff_body);

    // Her answer is still on screen. That is the whole claim: the synthesiser
    // died AFTER her validated words had crossed, so nothing was lost.
    await expect(page.getByTestId("call-captions").locator('[data-role="tara"]')).toBeVisible();

    // And the three controls are gone — a mute button on a call that has ended
    // as a call is a control over nothing.
    await expect(page.getByRole("button", { name: en.ui.call.mute })).toHaveCount(0);
  });

  test("the handoff opens the thread that already holds the call", async ({ page }) => {
    const client = await setupApi(page);
    await setupSocket(client, { behaviour: "tts_kill" });
    await open(page);

    await page.getByRole("button", { name: en.ui.call.handoff_open }).click();
    await expect(page).toHaveURL(/\/en\/ask(\?|$)/);
    await expect(page.getByTestId("ask")).toBeVisible();
  });

  test("a failed turn degrades rather than sitting there thinking", async ({ page }) => {
    const client = await setupApi(page);
    await setupSocket(client, { behaviour: "turn_failed" });
    await open(page);

    await expect(page.getByTestId("call-handoff")).toBeVisible();
    // The user's own words survived the failure — that is `commit_utterance`,
    // observable from the browser.
    await expect(page.getByTestId("call-captions").locator('[data-role="user"]')).toContainText(
      "Saturn",
    );
  });

  test("an exhausted pool hands off and never drops", async ({ page }) => {
    // §32.9: "at zero → auto text handoff with full context ... never a hard drop".
    const client = await setupApi(page);
    await setupSocket(client, { behaviour: "exhausted" });
    await open(page);

    await expect(page.getByTestId("call-handoff")).toBeVisible();
  });
});

test.describe("§7.3's plan chip and §32.9's warnings", () => {
  test("the five-minute notice is shown, in-locale, and is dismissible", async ({ page }) => {
    const client = await setupApi(page);
    await setupSocket(client, { behaviour: "warning" });
    await open(page);

    // §29.2: no countdown. The notice is a one-off sentence with a dismiss.
    const notice = page.getByRole("button", { name: /minute/ });
    await expect(notice.first()).toBeVisible();
    await notice.first().click();
  });

  test("the chip appears as the pool runs low and explains fair use", async ({ page }) => {
    // §25.3: the chip shows "N min left" as fair-use approaches, and tapping it
    // explains fair use in-locale. The stub grants 6 of 300, inside the 20%
    // band `CallControls` renders the meter for.
    const client = await setupApi(page);
    await setupSocket(client, { behaviour: "connecting" });
    await open(page);

    const chip = page.getByRole("button", { name: /minutes left/ });
    await expect(chip).toBeVisible();
    await chip.click();
    await expect(page.getByText(en.ui.call.fair_use_title)).toBeVisible();
  });
});

test.describe("the reasons a call is refused, at the door", () => {
  test("§33.5's flag renders as an explanation, not as a broken call", async ({ page }) => {
    const client = await setupApi(page, { scenario: "calls_disabled" });
    await setupSocket(client, { behaviour: "connecting" });
    await open(page);

    await expect(page.getByText(en.errors.voice.calls_not_enabled)).toBeVisible();
    // Non-retryable: `ErrorState` renders NO retry control for these, which is
    // right — pressing it again would not turn the release gate green.
    await expect(page.getByRole("button", { name: en.ui.retry })).toHaveCount(0);
  });

  test("CC-010 refuses a Hindi call and says voice notes still work", async ({ page }) => {
    // The ruling that matters most: an English recogniser fed Hindi audio does
    // not fail, it produces fluent nonsense that reaches §9 as the question.
    // So the call is refused before a socket exists.
    const client = await setupApi(page, { locale: "hi" });
    await setupSocket(client, { behaviour: "connecting", locale: "hi" });
    await open(page, `/hi/ask/call${SKIP_LAUNCH}`);

    // The HINDI string, because §2.4 forbids a silent English fallback — the
    // English one must NOT appear on a Hindi screen.
    // `.first()`: Next mounts its own `role="alert"` route announcer, so an
    // unscoped role query is ambiguous on every page in the app.
    await expect(page.getByRole("alert").first()).toBeVisible();
    await expect(page.getByText(hi.errors.voice.call_language_unavailable)).toBeVisible();
    await expect(page.getByText(en.errors.voice.call_language_unavailable)).toHaveCount(0);
  });

  test("an exhausted pool is refused before the call starts", async ({ page }) => {
    const client = await setupApi(page, { scenario: "call_minutes_exhausted" });
    await setupSocket(client, { behaviour: "connecting" });
    await open(page);

    await expect(page.getByText(en.errors.voice.minutes_exhausted)).toBeVisible();
  });
});
