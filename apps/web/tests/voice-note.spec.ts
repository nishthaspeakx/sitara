/**
 * §25.4's hold-to-record, with no browser and no server (`library` project).
 *
 * Everything hard about hold-to-record is a state question, and every one of
 * these has a wrong answer that ships: a 40ms brush becoming an empty bubble, a
 * release-while-locked stopping the recording the lock exists to continue, an
 * overshot cancel gesture locking instead of discarding.
 */

import { expect, test } from "@playwright/test";

import {
  CANCEL_THRESHOLD_PX,
  IDLE_VOICE_NOTE,
  LOCK_THRESHOLD_PX,
  MIN_NOTE_DURATION_MS,
  formatDuration,
  isRecording,
  voiceNoteReducer,
  type VoiceNoteAction,
  type VoiceNoteState,
} from "@/lib/voice-note";
import { MAX_NOTE_DURATION_MS } from "@sitara/schemas";

/** Drive the machine from idle. `startedAt` is 0 so `tick.at` reads as elapsed. */
function run(...actions: VoiceNoteAction[]): VoiceNoteState {
  return actions.reduce<VoiceNoteState>(
    (state, action) => voiceNoteReducer(state, action, 0),
    IDLE_VOICE_NOTE,
  );
}

const press: VoiceNoteAction = { type: "press", id: "m1", at: 0 };

test.describe("hold-to-record (§25.4, §28.3)", () => {
  test("a brush of the button sends nothing", async () => {
    const state = run(press, { type: "tick", at: MIN_NOTE_DURATION_MS - 1 }, { type: "release" });

    expect(state).toEqual(IDLE_VOICE_NOTE);
    // Silently: a toast for every accidental touch would be noise, and there
    // is nothing to tell the user about because nothing was sent.
    expect(state.noticeKey).toBeNull();
  });

  test("a real hold uploads on release", async () => {
    const state = run(press, { type: "tick", at: 3_000 }, { type: "release" });

    expect(state.phase).toBe("uploading");
    expect(state.clientMessageId).toBe("m1");
    expect(state.elapsedMs).toBe(3_000);
  });

  test("the message id is minted before any audio exists", async () => {
    // Every PCM frame must belong to a bubble the thread is already drawing,
    // or the transcript appears from nowhere when STT returns.
    const state = run(press);
    expect(state.clientMessageId).toBe("m1");
    expect(isRecording(state)).toBe(true);
  });

  test("releasing while locked keeps recording — that is what the lock is for", async () => {
    const locked = run(press, { type: "move", dx: 0, dy: -LOCK_THRESHOLD_PX }, { type: "release" });

    expect(locked.phase).toBe("locked");
    expect(isRecording(locked)).toBe(true);

    const stopped = voiceNoteReducer(locked, { type: "stop" }, 0);
    expect(stopped.phase).toBe("uploading");
  });

  test("the cancel-slide discards, and nothing leaves the device", async () => {
    const state = run(
      press,
      { type: "tick", at: 5_000 },
      { type: "move", dx: -CANCEL_THRESHOLD_PX, dy: 0 },
      { type: "release" },
    );

    expect(state).toEqual(IDLE_VOICE_NOTE);
  });

  test("an overshot cancel gesture cancels rather than locking", async () => {
    // Reaching left for cancel and drifting upward past the lock threshold is
    // an ordinary thing a thumb does. Locking there would start recording the
    // thing the user was trying to throw away.
    const state = run(press, {
      type: "move",
      dx: -CANCEL_THRESHOLD_PX,
      dy: -LOCK_THRESHOLD_PX,
    });

    expect(state.phase).toBe("cancelling");
  });

  test("the duration cap stops and sends rather than discarding", async () => {
    const state = run(press, { type: "tick", at: MAX_NOTE_DURATION_MS + 500 });

    // Two minutes of someone's voice thrown away is the worse of the two
    // failures. §34.6's cap exists because 16kHz PCM is near a document's
    // limit by then (§33.1), not because the words stopped mattering.
    expect(state.phase).toBe("uploading");
    expect(state.elapsedMs).toBe(MAX_NOTE_DURATION_MS);
    expect(state.noticeKey).toBe("ui.voice.too_long");
  });

  test("the cap comes from the schema, not a literal here", async () => {
    // A second declaration of the cap is how the client and the socket end up
    // disagreeing about what a valid note is.
    expect(MAX_NOTE_DURATION_MS).toBe(120_000);
  });

  test("a failed upload returns to idle and leaves the outcome to the bubble", async () => {
    const uploading = run(press, { type: "tick", at: 2_000 }, { type: "release" });
    const after = voiceNoteReducer(uploading, { type: "failed" }, 0);

    // `chat-thread.ts` owns what a failed send looks like — a `failed` message
    // with a retry. What must NOT happen is a mic stuck mid-air.
    expect(after).toEqual(IDLE_VOICE_NOTE);
  });

  test("durations format the way a bubble shows them", async () => {
    expect(formatDuration(0)).toBe("0:00");
    expect(formatDuration(7_400)).toBe("0:07");
    expect(formatDuration(63_000)).toBe("1:03");
    expect(formatDuration(MAX_NOTE_DURATION_MS)).toBe("2:00");
  });
});
