/**
 * §25.3's call, as a reducer over §34.6 events — no socket, no React, no audio.
 *
 * Same arrangement as `chat-thread.ts`, and for the same reason: which state
 * the screen is in, what the captions say, whether a warning has been shown,
 * and what a dropped socket does to a call in progress are all decisions that
 * should be checkable in milliseconds with no browser. `tests/call-state.spec.ts`
 * runs in the `library` project with no server at all.
 *
 * §25.3's six states are the whole vocabulary, and they are named here exactly
 * as the spec names them so a reader can check one list against the other:
 * connecting · speaking · listening · thinking · degraded · ended.
 */

import type { ControlEvent } from "@sitara/schemas";
import { HOLDING_PHRASE_AFTER_MS } from "@sitara/schemas";

export const CALL_STATES = [
  "connecting",
  "listening",
  "thinking",
  "speaking",
  "degraded",
  "ended",
] as const;
export type CallState = (typeof CALL_STATES)[number];

export interface CaptionLine {
  id: string;
  role: "user" | "tara";
  text: string;
  /** An interim STT result. Replaced by its final; never Tara's (§34.6). */
  partial: boolean;
}

export interface PlanChip {
  plan: string;
  unlimited: boolean;
  minutesLeft: number | null;
  minutesQuota: number | null;
}

export interface CallModel {
  state: CallState;
  /** Wall-clock ms the call has been connected. §25.3 puts it centre-screen. */
  startedAt: number | null;
  captions: CaptionLine[];
  captionsOn: boolean;
  muted: boolean;
  speakerOn: boolean;
  plan: PlanChip | null;
  /** §32.9's notice, one at a time. Cleared when the user acknowledges it. */
  warningKey: string | null;
  warningMinutes: number | null;
  /** §34.6's `handoff.to_text` — why the call became a thread. */
  handoffReason: string | null;
  conversationId: string | null;
  /** §32.11's one-tap offer, live only inside the resume window. */
  resumeOffered: boolean;
  error: { code: string; message_key: string } | null;
  /**
   * When `thinking` began. §25.3 caps the shimmer at 1.8s before she speaks a
   * holding phrase, and the constant is the schema package's so the server's
   * timer and this one cannot disagree.
   */
  thinkingSince: number | null;
}

export const IDLE_CALL: CallModel = {
  state: "connecting",
  startedAt: null,
  captions: [],
  captionsOn: false,
  muted: false,
  speakerOn: true,
  plan: null,
  warningKey: null,
  warningMinutes: null,
  handoffReason: null,
  conversationId: null,
  resumeOffered: false,
  error: null,
  thinkingSince: null,
};

export type CallAction =
  | { type: "event"; event: ControlEvent; at: number }
  | { type: "grant"; plan: PlanChip; captionsOn: boolean }
  | { type: "toggle"; control: "muted" | "speakerOn" | "captionsOn" }
  | { type: "dismiss_warning" }
  | { type: "socket_lost"; at: number }
  | { type: "end"; at: number };

/** Whether the shimmer has outstayed §25.3's welcome (`max 1.8s`). */
export function holdingPhraseDue(model: CallModel, now: number): boolean {
  return model.thinkingSince !== null && now - model.thinkingSince >= HOLDING_PHRASE_AFTER_MS;
}

function upsertCaption(captions: CaptionLine[], line: CaptionLine): CaptionLine[] {
  const index = captions.findIndex((c) => c.id === line.id && c.role === line.role);
  if (index === -1) return [...captions, line];
  // A final REPLACES its partial rather than appending beside it — the
  // recogniser corrects itself mid-sentence, and two lines saying nearly the
  // same thing reads as Tara mishearing twice.
  const next = [...captions];
  next[index] = line;
  return next;
}

export function callReducer(model: CallModel, action: CallAction): CallModel {
  switch (action.type) {
    case "grant":
      return { ...model, plan: action.plan, captionsOn: action.captionsOn };

    case "toggle":
      return { ...model, [action.control]: !model[action.control] };

    case "dismiss_warning":
      return { ...model, warningKey: null, warningMinutes: null };

    case "end":
      return { ...model, state: "ended", thinkingSince: null };

    case "socket_lost":
      // Not `ended`. §25.3's degraded state is a designed screen and an ended
      // call is a different one — a drop that rendered as a normal goodbye
      // would tell the user they hung up.
      return model.state === "ended"
        ? model
        : { ...model, state: "degraded", thinkingSince: null };

    case "event":
      return applyEvent(model, action.event, action.at);
  }
}

function applyEvent(model: CallModel, event: ControlEvent, at: number): CallModel {
  const payload = event.payload as Record<string, unknown>;

  switch (event.type) {
    case "session.ready":
      return {
        ...model,
        state: "listening",
        startedAt: model.startedAt ?? at,
        conversationId: (payload.conversation_id as string) ?? model.conversationId,
        error: null,
      };

    case "vad.state":
      // §25.3's mic-live indicator. `speech_end` does not return to a
      // different state — she may already be thinking — so only the start is
      // a transition the screen makes.
      return payload.state === "speech_start" && model.state !== "speaking"
        ? { ...model, state: "listening" }
        : model;

    case "presence.state": {
      const state = payload.state as string;
      if (state === "thoughtful") {
        return { ...model, state: "thinking", thinkingSince: model.thinkingSince ?? at };
      }
      if (state === "listening") return { ...model, state: "listening" };
      return model;
    }

    case "captions.partial":
      return {
        ...model,
        captions: upsertCaption(model.captions, {
          id: String(payload.client_message_id ?? ""),
          // The type pins this to the user's own speech, and so does this cast:
          // §9 validates AFTER generation, so a partial of Tara's words would be
          // pre-validation text on screen.
          role: "user",
          text: String(payload.text ?? ""),
          partial: true,
        }),
      };

    case "captions.final": {
      const role = payload.role === "tara" ? "tara" : "user";
      const turn = payload.turn as { text?: string } | undefined;
      return {
        ...model,
        // Her caption is the first moment the shimmer is over.
        thinkingSince: role === "tara" ? null : model.thinkingSince,
        captions: upsertCaption(model.captions, {
          id: String(payload.client_message_id ?? ""),
          role,
          text: role === "tara" ? String(turn?.text ?? "") : String(payload.text ?? ""),
          partial: false,
        }),
      };
    }

    case "tts.start":
      return { ...model, state: "speaking", thinkingSince: null };

    case "tts.end":
      return { ...model, state: model.state === "speaking" ? "listening" : model.state };

    case "barge_in":
      // Her audio stopped. Whether that is the user talking over her or a dead
      // synthesiser is `reason`'s job — and `handoff.to_text` follows for the
      // second, so this only has to stop looking like she is speaking.
      return { ...model, state: model.state === "speaking" ? "listening" : model.state };

    case "entitlement.warning":
      return {
        ...model,
        warningKey: String(payload.message_key ?? ""),
        warningMinutes: Number(payload.minutes_left ?? 0),
        plan: model.plan
          ? { ...model.plan, minutesLeft: Number(payload.minutes_left ?? 0) }
          : model.plan,
      };

    case "handoff.to_text":
      return {
        ...model,
        state: "degraded",
        thinkingSince: null,
        handoffReason: String(payload.reason ?? ""),
        conversationId: (payload.conversation_id as string) ?? model.conversationId,
      };

    case "resume.offer":
      return { ...model, resumeOffered: true };

    case "error":
      return {
        ...model,
        error: {
          code: String(payload.code ?? "SYS_INTERNAL"),
          message_key: String(payload.message_key ?? "errors.sys.internal"),
        },
      };

    default:
      return model;
  }
}
