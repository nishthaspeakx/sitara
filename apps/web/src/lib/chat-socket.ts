/**
 * The §34.6 client. Types from `@sitara/schemas`, never re-declared.
 *
 * ── Why the socket is not same-origin ──────────────────────────────────────
 *
 * Every HTTP call in this app goes to its own origin so §34.5's httpOnly
 * cookies are carried (`lib/api.ts` has the full reasoning). A WebSocket
 * cannot: Next evaluates its rewrites into a routes manifest at build time and
 * does not proxy an upgrade. So the socket is opened against
 * `sitara-realtime`'s origin, with a ticket minted by a cookie-authenticated
 * call to `POST /v1/chat/session` — single-use, 60 seconds, and it authorises
 * exactly one thing.
 *
 * **The `ws_url` is SERVED, not built here.** It used to be
 * `NEXT_PUBLIC_REALTIME_WS_URL`, inlined at build time. That is the same
 * mistake `NEXT_PUBLIC_API_BASE_URL` was: a public build-time origin that has
 * to agree with a cookie posture and a deployment topology, which means it is
 * a way for the two to disagree silently. The server knows where its own
 * socket is.
 *
 * ── What this file will not do ────────────────────────────────────────────
 *
 * It does not reconnect forever. §34.6's window is five minutes and §32.11
 * turns a recovery inside it into a one-tap resume; past that the server sends
 * `handoff.to_text` and the thread continues over `POST /v1/chat/turn`. A
 * client that retried indefinitely would keep a spinner alive over a
 * conversation that has already moved to a working transport.
 */

import type { ControlEvent, ControlEventType } from "@sitara/schemas";
import { RESUME_WINDOW_S } from "@sitara/schemas";

import { apiCall } from "./api";

export interface ChatSessionGrant {
  ticket: string;
  ws_url: string;
  resume_window_s: number;
}

export interface SocketHandlers {
  onEvent: (event: ControlEvent) => void;
  /** The socket closed. `willRetry` is false once the window has run out. */
  onClosed: (willRetry: boolean) => void;
}

/** Backoff between reconnects, in ms. Bounded by the resume window. */
const RETRY_DELAYS_MS = [500, 1_500, 4_000, 10_000, 20_000];

let seq = 0;
function nextSeq(): number {
  return seq++;
}

function frame(type: ControlEventType, payload: Record<string, unknown>): string {
  return JSON.stringify({ type, seq: nextSeq(), ts: Date.now(), ack: null, payload });
}

export class ChatSocket {
  private ws: WebSocket | null = null;
  private closedByUs = false;
  private attempt = 0;
  private openedAt = 0;
  private resumeToken: string | null = null;

  constructor(
    private readonly conversationId: string,
    private readonly locale: string,
    private readonly handlers: SocketHandlers,
  ) {}

  async connect(): Promise<void> {
    const grant = await apiCall<ChatSessionGrant>("/v1/chat/session", {
      method: "POST",
      body: JSON.stringify({ conversation_id: this.conversationId, locale: this.locale }),
    });
    if (!grant.ok) {
      this.handlers.onEvent({
        type: "error",
        seq: nextSeq(),
        ts: Date.now(),
        ack: null,
        payload: { ...grant.error },
      });
      this.handlers.onClosed(false);
      return;
    }
    this.open(grant.data);
  }

  private open(grant: ChatSessionGrant): void {
    const ws = new WebSocket(grant.ws_url);
    this.ws = ws;
    this.openedAt = this.openedAt || Date.now();

    ws.onopen = () => {
      ws.send(
        frame("session.start", {
          ticket: grant.ticket,
          conversation_id: this.conversationId,
          locale: this.locale,
          // Present last session's token so a completed turn comes back as a
          // resume offer rather than being asked again (§32.11).
          resume_token: this.resumeToken,
        }),
      );
    };

    ws.onmessage = (message) => {
      let event: ControlEvent;
      try {
        event = JSON.parse(String(message.data)) as ControlEvent;
      } catch {
        return;
      }
      if (event.type === "session.ready") {
        this.attempt = 0;
        const token = (event.payload as { resume_token?: unknown }).resume_token;
        if (typeof token === "string") this.resumeToken = token;
      }
      this.handlers.onEvent(event);
    };

    ws.onclose = () => {
      if (this.closedByUs) return;
      this.ws = null;
      const withinWindow = Date.now() - this.openedAt < RESUME_WINDOW_S * 1000;
      const delay = RETRY_DELAYS_MS[Math.min(this.attempt, RETRY_DELAYS_MS.length - 1)]!;
      const willRetry = withinWindow && this.attempt < RETRY_DELAYS_MS.length;
      this.handlers.onClosed(willRetry);
      if (!willRetry) return;
      this.attempt += 1;
      window.setTimeout(() => {
        // A new ticket every time: the old one was single-use and is 60
        // seconds old at best.
        void this.connect();
      }, delay);
    };
  }

  /** §25.4's finalised user turn. In a call STT finalises it; here the keyboard does. */
  send(text: string, clientMessageId: string, quotedMessageId?: string): boolean {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return false;
    this.ws.send(
      frame("captions.final", {
        role: "user",
        text,
        client_message_id: clientMessageId,
        quoted_message_id: quotedMessageId ?? null,
      }),
    );
    return true;
  }

  /**
   * Open §34.6's recording bracket (M9).
   *
   * The bracket is what binds the PCM about to follow to a bubble, a locale
   * and a consent posture — the server refuses binary outside one. Minting the
   * id here, before the first byte, is what stops the transcript appearing in
   * the thread from nowhere when STT returns.
   */
  startRecording(clientMessageId: string, quotedMessageId?: string): boolean {
    return this.vad("speech_start", clientMessageId, quotedMessageId);
  }

  /** One §34.6 binary frame: 8-byte header + 16 kHz mono s16le. */
  sendAudio(frameBuffer: ArrayBuffer): boolean {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return false;
    this.ws.send(frameBuffer);
    return true;
  }

  /** Close the bracket and ask for a transcript. */
  finishRecording(clientMessageId: string): boolean {
    return this.vad("speech_end", clientMessageId);
  }

  /**
   * §28.3's cancel-slide. The server discards without transcribing or storing.
   *
   * Sent even when the socket has gone: there is nothing to cancel on a dead
   * socket, and the client-side recorder discards its own buffer regardless —
   * so a failed send here is not a failure the user needs to hear about.
   */
  cancelRecording(clientMessageId: string): boolean {
    return this.vad("cancelled", clientMessageId);
  }

  private vad(state: string, clientMessageId: string, quotedMessageId?: string): boolean {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return false;
    this.ws.send(
      frame("vad.state", {
        state,
        client_message_id: clientMessageId,
        quoted_message_id: quotedMessageId ?? null,
      }),
    );
    return true;
  }

  close(): void {
    this.closedByUs = true;
    this.ws?.send(frame("session.end", {}));
    this.ws?.close();
    this.ws = null;
  }
}
