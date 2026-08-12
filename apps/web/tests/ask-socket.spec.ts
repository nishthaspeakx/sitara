import { expect, test, type Page } from "@playwright/test";

import en from "@sitara/i18n/messages/en.json" with { type: "json" };

import { SKIP_LAUNCH, setScenario, setupApi, setupSocket } from "./_onboarding-fixtures";

/**
 * S18 over a REAL WebSocket — including what the screen shows when it drops.
 *
 * ── Why a real socket ──────────────────────────────────────────────────────
 *
 * CL-013 forbids `page.route`, and a socket makes the point sharper: Playwright
 * cannot intercept a WebSocket at all, so the only browser-side option would be
 * to replace `window.WebSocket`. The suite would then be checking that the
 * client handles frames the test invented, over a transport that was never
 * opened — the handshake, the close, the reconnect and the ordering of frames
 * against the DOM they update would all be unobservable. Exactly the class of
 * blindness that let every onboarding step 404 with a green suite.
 *
 * So: browser → real upgrade → `scripts/stub-realtime.mjs`, whose turns are
 * RECORDED from the real §9 pipeline. A `close()` in that process is a real
 * close event in the client.
 *
 * ── What the ticket proves ─────────────────────────────────────────────────
 *
 * The socket origin is SERVED by `POST /v1/chat/session`, which travels the
 * real path: browser → `next start` → middleware → `/v1` rewrite → stub-api. So
 * these tests also cover the thing `NEXT_PUBLIC_REALTIME_WS_URL` would have
 * hidden — that the client asks the server where its socket is.
 */

const ASK = `/en/ask${SKIP_LAUNCH}`;

/**
 * Labels read from the catalog, not retyped.
 *
 * §25.4's retry control is "Send again", not "Retry" — a spec that matched
 * /retry/i passed nothing and would have gone on passing nothing if the string
 * had been "Retry" all along. Reading the key is how the assertion stays true
 * when the copy changes, which it will: these strings are reviewed in the §14
 * language pass.
 */
const SEND_AGAIN = en.ui.chat.retry;
/** The accessible name a citation underline carries (`ui.chat.open_trust`). */
const CITATION = /^Why Tara said/;

async function open(page: Page, path = ASK) {
  await page.goto(path);
  await expect(page.getByTestId("ask")).toBeVisible();
}

async function ask(page: Page, text = "what is Saturn doing?") {
  await page.getByTestId("composer").getByRole("textbox").fill(text);
  await page.getByTestId("composer").getByRole("textbox").press("Enter");
}

test.describe("§25.4 — a turn over the socket", () => {
  test("the reply arrives and the question is marked delivered", async ({ page }) => {
    const client = await setupApi(page);
    await setupSocket(client);
    await open(page);

    await ask(page);

    await expect(page.getByTestId("message-tara")).toBeVisible();
    await expect(page.getByTestId("message-tara")).toContainText(
      "Saturn is moving through your 10th house today",
    );
    // §25.4: ONE tick, meaning delivered to Tara. There is no second one.
    await expect(page.getByTestId("delivered")).toHaveCount(1);
  });

  test("the typing indicator follows real pipeline stages and then stops", async ({ page }) => {
    const client = await setupApi(page);
    // A held socket would be flaky; what is asserted is that the indicator is
    // GONE once the turn lands, which is the failure mode that matters — an
    // indicator that keeps animating over a finished or stalled turn.
    await setupSocket(client);
    await open(page);

    await ask(page);
    await expect(page.getByTestId("message-tara")).toBeVisible();
    await expect(page.getByTestId("typing-indicator")).toHaveCount(0);
  });

  test("a cited claim is underlined and opens the Trust Sheet in one tap", async ({ page }) => {
    /**
     * §30.4: "every astrological claim reachable to a Trust Sheet in ≤1 tap".
     * The span is the server's — computed by the grounding validator from where
     * it found the citation marker — so this also asserts the offsets survive
     * the trip.
     */
    const client = await setupApi(page);
    await setupSocket(client);
    await open(page);
    await ask(page);

    const cited = page.getByTestId("message-tara").getByRole("button", {
      name: /Saturn is moving through your 10th house today/,
    });
    await expect(cited).toBeVisible();
    await cited.click();

    const sheet = page.getByRole("dialog");
    await expect(sheet).toBeVisible();
    // §30.4's three layers, each saying something the others do not.
    await expect(sheet).toContainText("Saturn is moving through your 10th house today");
    await expect(sheet).not.toContainText("fact:");
  });

  test("two claims get two underlines, over the right words each", async ({ page }) => {
    const client = await setupApi(page);
    await setupSocket(client, { turn: "two_claims" });
    await open(page);
    await ask(page);

    const bubble = page.getByTestId("message-tara");
    await expect(bubble.getByRole("button", { name: /Saturn is in your 10th house/ })).toBeVisible();
    await expect(bubble.getByRole("button", { name: /Venus is in your 5th house/ })).toBeVisible();
  });

  test("a claimless reply carries no underline and no confidence chip", async ({ page }) => {
    /** A bubble with nothing to explain offers no explanation. */
    const client = await setupApi(page);
    await setupSocket(client, { turn: "claimless" });
    await open(page);
    await ask(page, "hello");

    const bubble = page.getByTestId("message-tara");
    await expect(bubble).toBeVisible();
    await expect(bubble.getByRole("button", { name: CITATION })).toHaveCount(0);
  });

  test("a fabricated claim never reaches the bubble", async ({ page }) => {
    /**
     * The recorded `fabricated` turn IS the pipeline's answer to a model that
     * invented a transit twice: §9 spends its one regeneration and serves the
     * safe fallback line. This asserts the screen shows that, and shows none of
     * what the model said.
     *
     * The pipeline-side half of this is
     * `services/api/tests/chat/test_presenter.py`, over the real §9 pipeline.
     */
    const client = await setupApi(page);
    await setupSocket(client, { turn: "fabricated" });
    await open(page);
    await ask(page);

    const bubble = page.getByTestId("message-tara");
    await expect(bubble).toBeVisible();
    await expect(bubble).not.toContainText("Jupiter");
    await expect(bubble).not.toContainText("7th house");
    await expect(bubble).not.toContainText("marriage");
    // Nothing to underline: the fallback line stands on no fact.
    await expect(bubble.getByRole("button", { name: CITATION })).toHaveCount(0);
  });
});

test.describe("§34.6 — what the screen shows when the socket drops mid-turn", () => {
  test("dropped before the answer: the question fails and offers a retry", async ({ page }) => {
    /**
     * The failure mode this test exists for is a bubble stuck on `sending`
     * forever — the shape of every chat client that has ever eaten a message.
     * §25.4's retry lives on the bubble, so the state has to reach it.
     */
    const client = await setupApi(page);
    await setupSocket(client, { behaviour: "drop_before_reply" });
    await open(page);
    await ask(page);

    await expect(page.getByRole("button", { name: SEND_AGAIN })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("message-tara")).toHaveCount(0);
    await expect(page.getByTestId("typing-indicator")).toHaveCount(0);
  });

  test("dropped after the answer: the answer stays, and is not asked again", async ({ page }) => {
    /**
     * §32.11: a completed turn is buffered, never re-run. Re-running would
     * charge the user twice for one question and could answer the same words
     * differently.
     */
    const client = await setupApi(page);
    await setupSocket(client, { behaviour: "drop_after_reply" });
    await open(page);
    await ask(page);

    await expect(page.getByTestId("message-tara")).toHaveCount(1);
    await expect(page.getByTestId("message-tara")).toContainText("Saturn");
    // The reconnect must not duplicate the reply into the thread.
    await page.waitForTimeout(2_000);
    await expect(page.getByTestId("message-tara")).toHaveCount(1);
  });

  test("past the window: the thread says so and keeps working over HTTP", async ({ page }) => {
    /**
     * §34.6 ends the resume window at five minutes and hands off to text with
     * full context. The banner is not decoration — the transport genuinely
     * changed — and the conversation continuing is what makes "full transcript
     * continuity" true rather than claimed.
     */
    const client = await setupApi(page);
    await setupSocket(client, { behaviour: "handoff" });
    await open(page);

    await expect(page.getByTestId("handoff-banner")).toBeVisible({ timeout: 15_000 });

    await ask(page);
    // Same recorded turn, delivered by `POST /v1/chat/turn` instead — one
    // `ChatTurn` on both transports is exactly what makes this invisible in
    // the thread's content.
    await expect(page.getByTestId("message-tara")).toContainText(
      "Saturn is moving through your 10th house today",
    );
  });

  test("a §34.4 envelope from the socket renders as an error, not a silent stall", async ({
    page,
  }) => {
    const client = await setupApi(page);
    await setupSocket(client, { behaviour: "error" });
    await open(page);
    await ask(page);

    // `.first()`: `errors.sys.unavailable` renders in ErrorState's heading and
    // its body, and a strict-mode locator counts both.
    await expect(
      page.getByText("Tara will be right back", { exact: false }).first(),
    ).toBeVisible();
    await expect(page.getByTestId("typing-indicator")).toHaveCount(0);
  });

  test("the session grant travels the real request path", async ({ page }) => {
    /**
     * `POST /v1/chat/session` is a `/v1` call, so it goes browser → next start
     * → middleware → rewrite → stub. A locale-prefixed `/en/v1/chat/session`
     * would 404 and the socket would never open — the exact defect CL-013 was
     * written about, in a new place.
     */
    const client = await setupApi(page);
    await setupSocket(client);
    const requests: string[] = [];
    page.on("request", (r) => {
      if (r.url().includes("/chat/session")) requests.push(r.url());
    });
    await open(page);
    await ask(page);
    await expect(page.getByTestId("message-tara")).toBeVisible();

    expect(requests.length).toBeGreaterThan(0);
    for (const url of requests) {
      expect(url).toContain("/v1/chat/session");
      expect(url).not.toContain("/en/v1/");
    }
  });

  test("no socket at all still leaves a working screen", async ({ page }) => {
    /** §8's ladder: the grant itself fails, so the thread starts on HTTP. */
    const client = await setupApi(page);
    await setupSocket(client);
    await setScenario(client, "chat_unavailable");
    await open(page);
    await ask(page);

    await expect(page.getByRole("button", { name: SEND_AGAIN })).toBeVisible({ timeout: 15_000 });
  });
});

test.describe("§22.9 — L3+ takes over the screen", () => {
  test("a crisis turn replaces the thread and offers only two exits", async ({ page }) => {
    /**
     * §29.1: the takeover "exits only to Ask Tara or Help — structurally never
     * to paywall, stories or marketing surfaces". Asserted over the rendered
     * subtree, so a screen cannot acquire a third exit unnoticed.
     */
    const client = await setupApi(page);
    await setupSocket(client, { turn: "crisis" });
    await open(page);
    await ask(page, "I want to kill myself");

    const takeover = page.getByTestId("safety-takeover");
    await expect(takeover).toBeVisible();

    // The thread, the composer and the tab bar are gone — a tab bar is four
    // other exits.
    await expect(page.getByTestId("thread")).toHaveCount(0);
    await expect(page.getByTestId("composer")).toHaveCount(0);
    await expect(page.getByRole("navigation")).toHaveCount(0);

    // §29.5: no portrait on the takeover — institutional calm.
    await expect(takeover.locator("img")).toHaveCount(0);

    const buttons = await takeover.getByRole("button").allInnerTexts();
    expect(buttons).toHaveLength(2);
  });

  test("/support/now renders the same screen", async ({ page }) => {
    /** §29.1's deep-link target for safety resources. One screen, not two. */
    await setupApi(page);
    await page.goto(`/en/support/now${SKIP_LAUNCH}`);
    await expect(page.getByTestId("safety-takeover")).toBeVisible();
  });
});

test.describe("§25.4 — what is deliberately absent", () => {
  test("no read receipts, no forwarded labels, no group mechanics", async ({ page }) => {
    const client = await setupApi(page);
    await setupSocket(client);
    await open(page);
    await ask(page);
    await expect(page.getByTestId("message-tara")).toBeVisible();

    const body = (await page.getByTestId("ask").innerText()).toLowerCase();
    expect(body).not.toContain("read");
    expect(body).not.toContain("forwarded");
    expect(body).not.toContain("last seen");
    expect(body).not.toContain("online");
    // One tick per sent message, and only one.
    await expect(page.getByTestId("delivered")).toHaveCount(1);
  });

  test("voice notes are dark until M9", async ({ page }) => {
    /**
     * `VoiceBar` and `VoiceNoteBubble` are built and screenshotted in the §24.3
     * library; what is missing is §33.1's encrypted storage of the ORIGINAL
     * recording, without which §25.4's "replay plays the user's original
     * recording, never a TTS reconstruction" cannot be honoured.
     */
    const client = await setupApi(page);
    await setupSocket(client);
    await open(page);

    const composer = page.getByTestId("composer");
    await expect(composer.getByRole("button", { name: /record|voice|mic/i })).toHaveCount(0);
    await expect(page.getByTestId("voice-bar")).toHaveCount(0);
  });
});
