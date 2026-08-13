/**
 * §25.4's hold-to-record, as a state machine.
 *
 * No microphone, no socket, no React — the same discipline `chat-thread.ts`
 * follows, and for the same payoff: everything that is hard about hold-to-record
 * is here and testable by calling a function. Whether a 90ms tap starts a
 * recording, what a slide-left does mid-hold, whether releasing after a lock
 * sends or keeps recording, what happens at the duration cap.
 *
 * §28.3's controls column, exactly: `hold/lock · cancel-slide · speed 1/1.5/2×`.
 *
 * The one rule worth stating up front, because it is the difference between a
 * cancel a user trusts and one they do not: **`cancelled` is terminal and
 * discards.** Nothing is transcribed, nothing is stored, nothing is uploaded.
 * For something a person said out loud, any other reading of "cancel" is a
 * broken promise.
 */

import { MAX_NOTE_DURATION_MS } from "@sitara/schemas";

export type VoiceNotePhase =
  /** Nothing is happening; the mic button is idle. */
  | "idle"
  /** A finger is down. Releasing SENDS (if long enough) or cancels (if not). */
  | "holding"
  /** Slid up past the lock threshold — the finger can leave, recording continues. */
  | "locked"
  /** Slid toward the cancel affordance; releasing here discards. */
  | "cancelling"
  /** The bytes are with the server; the bubble shows `sending`. */
  | "uploading";

export interface VoiceNoteState {
  phase: VoiceNotePhase;
  /** Milliseconds recorded so far, from the caller's clock — never `Date.now()`. */
  elapsedMs: number;
  /** Client-minted BEFORE the first byte, so every frame belongs to a bubble. */
  clientMessageId: string | null;
  /** §25.4's swipe-to-reply, carried through the recording. */
  quotedId?: string;
  /** Set when the cap is reached, so the composer can say so in-locale. */
  noticeKey: string | null;
}

export const IDLE_VOICE_NOTE: VoiceNoteState = {
  phase: "idle",
  elapsedMs: 0,
  clientMessageId: null,
  noticeKey: null,
};

/**
 * Below this, a press is a TAP and not a recording.
 *
 * Without it the mic button is unusable: every accidental brush produces a
 * 40ms note, which uploads, transcribes to nothing, and puts an empty bubble
 * in the thread. WhatsApp's own threshold is around here for the same reason.
 */
export const MIN_NOTE_DURATION_MS = 500;

/** Vertical drag (px) past which the recording locks and the finger can leave. */
export const LOCK_THRESHOLD_PX = 48;

/** Horizontal drag (px) toward the cancel affordance before release discards. */
export const CANCEL_THRESHOLD_PX = 72;

export type VoiceNoteAction =
  | { type: "press"; id: string; at: number; quotedId?: string }
  | { type: "move"; dx: number; dy: number }
  | { type: "tick"; at: number }
  | { type: "release" }
  | { type: "stop" }
  | { type: "cancel" }
  | { type: "uploaded" }
  | { type: "failed" };

export function voiceNoteReducer(
  state: VoiceNoteState,
  action: VoiceNoteAction,
  startedAt = 0,
): VoiceNoteState {
  switch (action.type) {
    case "press":
      return {
        phase: "holding",
        elapsedMs: 0,
        clientMessageId: action.id,
        quotedId: action.quotedId,
        noticeKey: null,
      };

    case "move": {
      if (state.phase !== "holding" && state.phase !== "cancelling") return state;
      // Cancel wins over lock when both thresholds are crossed: a user
      // reaching for cancel and overshooting must not end up locked into
      // recording the thing they were trying to discard.
      if (action.dx <= -CANCEL_THRESHOLD_PX) return { ...state, phase: "cancelling" };
      if (action.dy <= -LOCK_THRESHOLD_PX) return { ...state, phase: "locked" };
      return { ...state, phase: "holding" };
    }

    case "tick": {
      if (state.phase !== "holding" && state.phase !== "locked" && state.phase !== "cancelling") {
        return state;
      }
      const elapsedMs = action.at - startedAt;
      if (elapsedMs >= MAX_NOTE_DURATION_MS) {
        // The cap stops here rather than discarding: the user has said two
        // minutes of something and throwing it away would be the worse of the
        // two failures. §34.6's cap exists because 16kHz PCM at two minutes is
        // already near what a Mongo document can hold (§33.1).
        return {
          ...state,
          phase: "uploading",
          elapsedMs: MAX_NOTE_DURATION_MS,
          noticeKey: "ui.voice.too_long",
        };
      }
      return { ...state, elapsedMs };
    }

    case "release": {
      // A release while locked does NOT stop the recording — that is what the
      // lock is for. Only `stop` ends a locked note.
      if (state.phase === "locked") return state;
      if (state.phase === "cancelling") return { ...IDLE_VOICE_NOTE };
      if (state.phase !== "holding") return state;
      // Too short to be speech. Discarded silently: a toast for every brush of
      // the button would be noise, and nothing was sent.
      if (state.elapsedMs < MIN_NOTE_DURATION_MS) return { ...IDLE_VOICE_NOTE };
      return { ...state, phase: "uploading" };
    }

    case "stop":
      if (state.phase !== "locked") return state;
      return { ...state, phase: "uploading" };

    case "cancel":
      return { ...IDLE_VOICE_NOTE };

    case "uploaded":
    case "failed":
      // The bubble owns the outcome from here (`chat-thread.ts`): a failed
      // upload leaves a `failed` message with a retry, not a mic stuck mid-air.
      return { ...IDLE_VOICE_NOTE };
  }
}

/** `0:07` — the duration a bubble shows. Formatted here so one rule serves the
 * recording indicator and the played-back note. */
export function formatDuration(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

/** Whether this state should be sending PCM up the socket right now. */
export function isRecording(state: VoiceNoteState): boolean {
  return state.phase === "holding" || state.phase === "locked" || state.phase === "cancelling";
}
