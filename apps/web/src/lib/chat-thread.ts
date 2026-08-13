/**
 * The thread, as a reducer over §34.6 events.
 *
 * No socket, no React, no browser — which is the point. Everything that is
 * hard about a chat screen is here: which bubble a reply belongs to, what a
 * dropped socket does to a message still in flight, whether a resumed turn
 * appears once or twice. All of it is testable by calling a function.
 *
 * §25.4's grammar, and what is deliberately absent from it:
 *
 * **A single ✓ means delivered to Tara, and nothing more.** There are no read
 * receipts and no blue ticks — §25.4 calls them "meaningless and manipulative
 * for an AI", and the type below has no state that could express one. Delivery
 * is the server acking the seq that carried the message; "read" is not a thing
 * an AI does to a message.
 *
 * **A message in flight is never lost silently.** If the socket dies mid-turn
 * the bubble goes to `failed` and grows a retry — the affordance `ChatBubble`
 * already has. What it must not do is sit on `sending` forever, which is the
 * shape of every chat client that has ever eaten a message.
 */

import type {
  ChatTurn,
  ControlEvent,
  PlaybackPolicy,
  PresenceState,
  TranscriptStatus,
} from "@sitara/schemas";

/**
 * §25.4's ticks, and the whole of them.
 *
 *   sending    left this client, not yet acked
 *   delivered  Tara has it — ONE tick, and no state after it
 *   failed     the socket went away before an answer; retry lives on the bubble
 */
export type DeliveryState = "sending" | "delivered" | "failed";

export interface UserMessage {
  kind: "user";
  /** Client-minted, so a reply can find its question across a reconnect. */
  id: string;
  text: string;
  at: number;
  delivery: DeliveryState;
  /** §25.4 swipe-to-reply — the id of the message this quotes. */
  quotedId?: string;
  /**
   * §25.4/§33.1's voice note. Present only when the user SPOKE this turn.
   *
   * There is deliberately no field here that could carry a TTS asset id.
   * §25.4's promise is that replay plays the user's own recording "never a TTS
   * reconstruction", and the way that breaks is a wiring mistake, not a
   * decision — so the user bubble has no prop the mistake could travel in.
   * Her audio lives on `TaraMessage.audio` and nowhere else.
   */
  voice?: UserVoiceNote;
}

export interface UserVoiceNote {
  /** §6.4's `source_audio_asset_id`. Null once expired or never stored. */
  assetId: string | null;
  durationMs: number;
  transcriptStatus: TranscriptStatus;
  /** Decides whether the bubble offers playback at all (§33.1). */
  playbackPolicy: PlaybackPolicy;
  /** ISO instant the original is deleted on — §33.1's 30-day promise, shown. */
  expiresAt?: string | null;
}

export interface TaraMessage {
  kind: "tara";
  id: string;
  turn: ChatTurn;
  at: number;
  /** The user message this answers, so a resumed turn cannot duplicate. */
  replyTo: string;
  /**
   * §25.4: "Tara's replies arrive as voice-note bubbles rendered from her TTS
   * with transcript toggle — this is the voice-adoption engine."
   *
   * Set from `tts.start`/`tts.end`, which the server sends AFTER her
   * `captions.final` — so `turn.text` (the transcript the toggle shows) is
   * already here, and is the same validated text the audio was rendered from.
   */
  audio?: TaraVoiceReply;
}

export interface TaraVoiceReply {
  assetId: string;
  durationMs: number;
}

export type Message = UserMessage | TaraMessage;

/** What the composer and the header need to know. */
export interface ThreadState {
  messages: Message[];
  /** Non-null while Tara is working. Drives the typing/listening indicator. */
  presence: PresenceState | null;
  /** §34.6's session token for a reconnect inside the resume window. */
  resumeToken: string | null;
  /**
   * The socket gave up and the thread continues over `POST /v1/chat/turn`
   * (§32.11). A banner says so — the conversation is not interrupted, but
   * pretending nothing changed would be the "fake online status" §25.4
   * refuses, pointed the other way.
   */
  handedOffToText: boolean;
  /** A §34.4 envelope the screen must render. Cleared on the next send. */
  error: { code: string; message_key: string } | null;
  /** True once the socket has answered `session.ready`. */
  connected: boolean;
}

export const EMPTY_THREAD: ThreadState = {
  messages: [],
  presence: null,
  resumeToken: null,
  handedOffToText: false,
  error: null,
  connected: false,
};

export type ThreadAction =
  | { type: "send"; id: string; text: string; at: number; quotedId?: string }
  | { type: "speak"; id: string; at: number; durationMs: number; quotedId?: string }
  | { type: "event"; event: ControlEvent; at: number }
  | { type: "socket_lost"; at: number }
  | { type: "handoff_reply"; turn: ChatTurn; replyTo: string; at: number }
  | { type: "handoff_failed"; replyTo: string; error: { code: string; message_key: string } };

function isPresenceState(value: unknown): value is PresenceState {
  return typeof value === "string";
}

/** Append a Tara turn unless the question already has an answer. */
function withReply(
  messages: Message[],
  turn: ChatTurn,
  replyTo: string,
  at: number,
): Message[] {
  // §32.11's resume offer can arrive for a turn the client already received —
  // a socket that dropped AFTER the frame left the server, then reconnected.
  // Keying on the question rather than appending blindly is what makes the
  // resume idempotent from the thread's point of view.
  if (messages.some((m) => m.kind === "tara" && m.replyTo === replyTo)) return messages;
  return [
    ...messages.map((m) =>
      m.kind === "user" && m.id === replyTo ? { ...m, delivery: "delivered" as const } : m,
    ),
    { kind: "tara", id: turn.message_id || `tara-${replyTo}`, turn, at, replyTo },
  ];
}

/**
 * Fill the voice bubble the finger already created (§25.4).
 *
 * `playback_policy` is served, never inferred. A client that decided for itself
 * whether a recording exists would guess wrong in exactly §33.1's two
 * interesting cases — the ephemeral account and the note whose thirty days are
 * up — and would render a play control over nothing.
 */
function withTranscript(state: ThreadState, payload: Record<string, unknown>): ThreadState {
  const id = String(payload.client_message_id ?? "");
  return {
    ...state,
    messages: state.messages.map((m) =>
      m.kind === "user" && m.id === id
        ? {
            ...m,
            text: String(payload.text ?? ""),
            delivery: "delivered" as const,
            voice: {
              assetId: (payload.source_audio_asset_id as string | null) ?? null,
              durationMs: Number(payload.duration_ms ?? m.voice?.durationMs ?? 0),
              transcriptStatus: payload.transcript_status as TranscriptStatus,
              playbackPolicy: payload.playback_policy as PlaybackPolicy,
              expiresAt: (payload.source_audio_expires_at as string | null) ?? null,
            },
          }
        : m,
    ),
  };
}

export function threadReducer(state: ThreadState, action: ThreadAction): ThreadState {
  switch (action.type) {
    case "send":
      return {
        ...state,
        error: null,
        messages: [
          ...state.messages,
          {
            kind: "user",
            id: action.id,
            text: action.text,
            at: action.at,
            delivery: "sending",
            quotedId: action.quotedId,
          },
        ],
      };

    case "speak":
      // §25.4's voice bubble exists from the moment the finger lifts, with no
      // text in it: the transcript arrives seconds later on `captions.final`.
      // Creating it now is what gives every PCM frame a bubble to belong to,
      // and what stops the note appearing from nowhere when STT returns.
      return {
        ...state,
        error: null,
        messages: [
          ...state.messages,
          {
            kind: "user",
            id: action.id,
            text: "",
            at: action.at,
            delivery: "sending",
            quotedId: action.quotedId,
            voice: {
              assetId: null,
              durationMs: action.durationMs,
              transcriptStatus: "pending",
              // Nothing is stored yet, so the bubble promises no playback.
              // `captions.final` upgrades this once the server says where the
              // recording landed — or leaves it, in §33.1's ephemeral mode.
              playbackPolicy: "transcript_only",
            },
          },
        ],
      };

    case "socket_lost": {
      // A turn that was in flight has no answer coming on THIS socket. The
      // bubble says so rather than spinning: an indicator that keeps animating
      // through a dead socket is the same lie as a fake "online".
      return {
        ...state,
        connected: false,
        presence: null,
        messages: state.messages.map((m) =>
          m.kind === "user" && m.delivery === "sending" ? { ...m, delivery: "failed" } : m,
        ),
      };
    }

    case "handoff_reply":
      return {
        ...state,
        presence: null,
        messages: withReply(state.messages, action.turn, action.replyTo, action.at),
      };

    case "handoff_failed":
      return {
        ...state,
        presence: null,
        error: action.error,
        messages: state.messages.map((m) =>
          m.kind === "user" && m.id === action.replyTo ? { ...m, delivery: "failed" } : m,
        ),
      };

    case "event":
      return applyEvent(state, action.event, action.at);
  }
}

function applyEvent(state: ThreadState, event: ControlEvent, at: number): ThreadState {
  const payload = event.payload as Record<string, unknown>;

  switch (event.type) {
    case "session.ready":
      return {
        ...state,
        connected: true,
        handedOffToText: false,
        resumeToken:
          typeof payload.resume_token === "string" ? payload.resume_token : state.resumeToken,
      };

    case "presence.state":
      return {
        ...state,
        presence: isPresenceState(payload.state) ? payload.state : state.presence,
      };

    case "captions.final": {
      // §34.6's user direction was inbound-never until M9. It is now the
      // FINALISED TRANSCRIPT of a voice note: the words the user spoke, plus
      // where their recording was stored. It fills a bubble that already
      // exists rather than appending one (`speak` created it).
      if (payload.role === "user") return withTranscript(state, payload);
      if (payload.role !== "tara") return state;
      const turn = payload.turn as ChatTurn | undefined;
      const replyTo = String(payload.client_message_id ?? "");
      if (!turn) return state;
      return {
        ...state,
        presence: null,
        error: null,
        messages: withReply(state.messages, turn, replyTo, at),
      };
    }

    case "resume.offer": {
      const turn = payload.pending_turn as ChatTurn | null | undefined;
      const replyTo = String(payload.pending_client_message_id ?? "");
      if (!turn) return state;
      return {
        ...state,
        presence: null,
        messages: withReply(state.messages, turn, replyTo, at),
      };
    }

    case "handoff.to_text":
      return { ...state, connected: false, presence: null, handedOffToText: true };

    case "error": {
      const code = String(payload.code ?? "SYS_INTERNAL");
      const message_key = String(payload.message_key ?? "errors.sys.internal");
      return {
        ...state,
        presence: null,
        error: { code, message_key },
        // The question that provoked it is the one still in flight.
        messages: state.messages.map((m) =>
          m.kind === "user" && m.delivery === "sending" ? { ...m, delivery: "failed" } : m,
        ),
      };
    }

    case "tts.start":
    case "tts.end": {
      // §25.4's voice-adoption engine. Both members carry `client_message_id`,
      // which is the QUESTION's id — her bubble is found by `replyTo`, the
      // same key `withReply` used to place it.
      const replyTo = String(payload.client_message_id ?? "");
      return {
        ...state,
        messages: state.messages.map((m) =>
          m.kind === "tara" && m.replyTo === replyTo
            ? {
                ...m,
                audio: {
                  assetId: String(payload.tts_audio_asset_id ?? m.audio?.assetId ?? ""),
                  durationMs: Number(payload.duration_ms ?? m.audio?.durationMs ?? 0),
                },
              }
            : m,
        ),
      };
    }

    // `captions.partial`, `vad.state`, `barge_in` and `entitlement.warning`
    // reach here. The first two are the client's own echo; the last two belong
    // to live calls (M10). Ignored rather than switched on exhaustively, so
    // M10 adding behaviour is an addition and not a rewrite.
    default:
      return state;
  }
}

/**
 * §25.4's date pills. Grouped by LOCAL day, formatted by the caller — a pill
 * computed from a UTC date puts the divider in the wrong place for half the
 * world for half the day.
 */
export function groupByDay(messages: Message[]): Array<{ day: string; items: Message[] }> {
  const groups: Array<{ day: string; items: Message[] }> = [];
  for (const message of messages) {
    const day = new Date(message.at).toDateString();
    const last = groups[groups.length - 1];
    if (last && last.day === day) last.items.push(message);
    else groups.push({ day, items: [message] });
  }
  return groups;
}
