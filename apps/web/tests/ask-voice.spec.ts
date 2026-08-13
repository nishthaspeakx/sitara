import { expect, test, type Page } from "@playwright/test";

import en from "@sitara/i18n/messages/en.json" with { type: "json" };

import { SKIP_LAUNCH, setupApi, setupSocket } from "./_onboarding-fixtures";

/**
 * §25.4's voice notes, over a REAL socket carrying REAL audio.
 *
 * This spec replaces `ask-voice-dark.spec.ts`, which `features.ts` cited for
 * two milestones as the mechanical proof that nothing rendered while the flag
 * was false. **That file never existed**, and the gate it named was
 * `{VOICE_NOTES_ENABLED ? null : null}` — a no-op reading as enforcement. So
 * this file starts from the opposite posture: everything below is observed, not
 * asserted about an absence.
 *
 * ── Why a fake DEVICE and not a fake recorder ─────────────────────────────
 *
 * `--use-fake-device-for-media-stream` gives Chromium a real audio pipeline
 * with synthetic input: `getUserMedia` resolves, the AudioWorklet runs, and the
 * bytes reaching `stub-realtime.mjs` are bytes the browser actually produced.
 * Stubbing `VoiceRecorder` instead would verify that the client sends frames
 * the test invented, over a capture path that never opened — the same blindness
 * CL-013 names, one layer further in. The socket half already refuses to be
 * faked (Playwright cannot intercept a WebSocket at all); the microphone half
 * should not be either.
 *
 * The stub enforces §34.6's bracket rule exactly as `services/realtime` does —
 * audio outside a `vad.state` is SYS_VALIDATION, a sequence gap fails the note
 * — because a stub that accepted what the real service refuses is a fake that
 * accepts what the real system rejects.
 */

test.use({
  permissions: ["microphone"],
  launchOptions: {
    args: [
      "--use-fake-device-for-media-stream",
      // Without this the permission prompt blocks even with `permissions`
      // granted, because the fake device still goes through the picker.
      "--use-fake-ui-for-media-stream",
      "--autoplay-policy=no-user-gesture-required",
    ],
  },
});

const ASK = `/en/ask${SKIP_LAUNCH}`;

/** Read from the catalog, never retyped — the §14 language pass will move these. */
const HOLD_TO_SPEAK = en.ui.voice.idle;
const VOICE_INPUT = en.ui.audio.voice_input;
const TRANSCRIPT = "Mera rahu kaal kab hai aaj?";

async function open(page: Page): Promise<void> {
  await page.goto(ASK);
  await expect(page.getByTestId("ask")).toBeVisible();
  // The bracket cannot open before the socket is up — `startRecording` returns
  // false on a closed socket and the bubble would never appear.
  await expect(page.getByTestId("ask")).toHaveAttribute("data-connected", "true");
}

function mic(page: Page) {
  return page.getByRole("button", { name: HOLD_TO_SPEAK });
}

/**
 * Hold the mic for `ms` of ACTUAL recording, then release.
 *
 * The wait starts when the elapsed counter appears, not when the pointer lands.
 * `getUserMedia` plus an AudioWorklet module fetch is 50–200ms idle and a good
 * deal more with four workers competing, and the recording clock starts when
 * audio does — so timing from `mouse.down` produced a note shorter than the
 * 500ms speech threshold under load, which the reducer then correctly
 * discarded. The test passed alone and failed in the full suite, which is the
 * signature of a timing assumption rather than a defect.
 */
async function hold(page: Page, ms = 900): Promise<void> {
  const button = mic(page);
  const box = await button.boundingBox();
  if (!box) throw new Error("the mic affordance is not on screen");
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await expect(page.getByTestId("voice-elapsed")).toBeVisible();
  await page.waitForTimeout(ms);
  await page.mouse.up();
}

test.describe("voice notes (§25.4, §33.1)", () => {
  test("a held note becomes a transcript and a voice-note reply", async ({ page }) => {
    const client = await setupApi(page);
    await setupSocket(client, { turn: "grounded", transcript: TRANSCRIPT });
    await open(page);

    await hold(page);

    // The user's own bubble carries the transcript STT produced...
    await expect(page.getByText(TRANSCRIPT)).toBeVisible();
    // ...and her reply follows it, from the recorded §9 turn.
    await expect(page.getByText(/Saturn/i).first()).toBeVisible();

    // §25.4's playback control points at the ORIGINAL recording — the asset id
    // the server stored, never `tts_audio_asset_id`. This is the assertion the
    // whole milestone exists to make true.
    const audio = page.locator('audio[src*="/v1/voice/notes/"]').first();
    await expect(audio).toHaveAttribute("src", /6a70000000000000000000e1/);
    await expect(audio).not.toHaveAttribute("src", /6a70000000000000000000e2/);
  });

  test("a brush of the mic sends nothing at all", async ({ page }) => {
    const client = await setupApi(page);
    await setupSocket(client, { turn: "grounded", transcript: TRANSCRIPT });
    await open(page);

    // Deliberately NOT `hold()`: that waits for recording to start, and this
    // test is about a press that never should. A raw down/up is the gesture.
    const box = await mic(page).boundingBox();
    if (!box) throw new Error("the mic affordance is not on screen");
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.up();

    // No bubble, no transcript, no error. §25.4's threshold exists because
    // every accidental touch would otherwise upload an empty note.
    await expect(page.getByText(TRANSCRIPT)).toHaveCount(0);
    await expect(page.getByTestId("error-state")).toHaveCount(0);
  });

  test("§33.1's ephemeral mode shows the transcript and offers no playback", async ({ page }) => {
    const client = await setupApi(page);
    await setupSocket(client, {
      turn: "grounded",
      transcript: TRANSCRIPT,
      behaviour: "ephemeral_audio",
    });
    await open(page);

    await hold(page);

    await expect(page.getByText(TRANSCRIPT)).toBeVisible();
    // "the bubble UI honestly drops playback of expired/deleted audio and shows
    // the transcript with a 'voice input' marker" — §33.1, verbatim.
    await expect(page.getByTestId("voice-input-marker")).toHaveText(VOICE_INPUT);
    // No element at all, rather than a disabled control: a greyed play button
    // still says "there is a recording here", which is what stopped being true.
    await expect(page.locator('audio[src*="/v1/voice/notes/"]')).toHaveCount(0);
  });

  test("a failed transcription keeps the recording and raises no error", async ({ page }) => {
    const client = await setupApi(page);
    await setupSocket(client, { turn: "grounded", behaviour: "transcribe_fail" });
    await open(page);

    await hold(page);

    // §28.3: "transcribe-fail → 'send as text?' original audio preserved". A
    // designed state on the user's own bubble, NOT an error envelope — that
    // would put a retry control over a note that recorded and stored fine.
    await expect(page.getByText(en.ui.audio.transcript_failed)).toBeVisible();
    await expect(page.getByTestId("error-state")).toHaveCount(0);
    await expect(page.locator('audio[src*="/v1/voice/notes/"]')).toHaveCount(1);
  });

  test("a TTS outage still delivers her answer, as text", async ({ page }) => {
    const client = await setupApi(page);
    await setupSocket(client, {
      turn: "grounded",
      transcript: TRANSCRIPT,
      behaviour: "no_tts",
    });
    await open(page);

    await hold(page);

    // §8/§30.1: synthesis is an enhancement of a turn that is already validated
    // and stored. Losing it must not lose the reply she already gave.
    await expect(page.getByText(/Saturn/i).first()).toBeVisible();
    await expect(page.getByTestId("error-state")).toHaveCount(0);
  });

  test("the elapsed counter is announced, not only drawn", async ({ page }) => {
    const client = await setupApi(page);
    await setupSocket(client, { turn: "grounded", transcript: TRANSCRIPT });
    await open(page);

    const button = mic(page);
    const box = await button.boundingBox();
    if (!box) throw new Error("the mic affordance is not on screen");
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();

    // §24.3's rule that state is never colour alone, and WCAG 2.2 AA: the
    // waveform is `aria-hidden`, so the duration has to carry the state in
    // words on a live region.
    const elapsed = page.getByTestId("voice-elapsed");
    await expect(elapsed).toBeVisible();
    await expect(elapsed).toHaveText(/^0:0\d$/);

    await page.mouse.up();
  });

  test("the composer keeps working while the mic is on screen", async ({ page }) => {
    const client = await setupApi(page);
    await setupSocket(client, { turn: "grounded" });
    await open(page);

    // §30.1: text always works. The mic is beside the field, never instead of
    // it — the affordance that can fail is not the only way forward.
    await expect(mic(page)).toBeVisible();
    const field = page.getByTestId("composer").getByRole("textbox");
    await field.fill("what is Saturn doing?");
    await field.press("Enter");

    await expect(page.getByText(/Saturn/i).first()).toBeVisible();
  });
});
