/**
 * The §34.6 call client (M9-P10b, §25.3).
 *
 * A sibling of `chat-socket.ts` rather than a mode of it. The two share a
 * protocol and almost nothing else: a chat sends bursts of text and a call
 * holds a microphone open for minutes, plays audio back with a jitter buffer,
 * and is metered. Folding them together would have meant one class where half
 * the fields are null in either mode.
 *
 * **Everything that can refuse a call refuses it before this class exists.**
 * `POST /v1/call/session` evaluates §33.5's flag, CC-010's locale ruling and
 * §7.3's pool, so a grant is proof the call may happen. That is why `connect`
 * surfaces a refusal as an error the SCREEN renders rather than as a call that
 * starts and then dies.
 *
 * ── The audio, in both directions ──────────────────────────────────────────
 *
 * Up: 16 kHz mono s16le with §34.6's 8-byte header, from the same
 * `VoiceRecorder` the voice notes use — one capture path, one resampler, one
 * set of quirks to know about.
 *
 * Down: her reply, played through a small scheduled queue. It is a QUEUE and
 * not an `<audio>` element because §25.3's barge-in has to be able to drop what
 * has not been played yet: an element that had already buffered three seconds
 * would keep talking over the user for three seconds after the server stopped
 * sending, which is precisely the failure barge-in exists to prevent.
 */

import type { ControlEvent, ControlEventType } from "@sitara/schemas";
import { BINARY_SAMPLE_RATE_HZ, RESUME_WINDOW_S } from "@sitara/schemas";

import { apiCall } from "./api";
import { VoiceRecorder } from "./voice-recorder";

export interface CallGrant {
  ticket: string;
  ws_url: string;
  resume_window_s: number;
  entitlement: {
    plan: string;
    unlimited: boolean;
    minutes_left: number | null;
    minutes_quota: number | null;
  };
  captions_default_on: boolean;
}

export interface CallHandlers {
  onEvent: (event: ControlEvent) => void;
  onGrant: (grant: CallGrant) => void;
  onClosed: () => void;
  onRefused: (error: { code: string; message_key: string }) => void;
}

const RETRY_DELAYS_MS = [500, 1_500, 4_000, 10_000];

let seq = 0;
function frame(type: ControlEventType, payload: Record<string, unknown>): string {
  return JSON.stringify({ type, seq: seq++, ts: Date.now(), ack: null, payload });
}

/**
 * Plays streamed PCM with a jitter buffer short enough to interrupt.
 *
 * `AudioContext` rather than MediaSource: the frames are raw PCM at a known
 * rate (no container to demux), and scheduling each buffer explicitly is what
 * makes `drop()` able to silence everything not yet audible.
 */
class PcmPlayer {
  private context: AudioContext | null = null;
  private playAt = 0;
  private sources: AudioBufferSourceNode[] = [];

  private ensure(): AudioContext {
    this.context ??= new AudioContext({ sampleRate: BINARY_SAMPLE_RATE_HZ });
    // **Resume, every time.** The context is created lazily inside `push`,
    // which runs from a WebSocket message handler — not a user gesture — so
    // Chrome's autoplay policy creates it SUSPENDED and every buffer is
    // scheduled into silence. The call looks perfect: frames arrive,
    // `tts.chunk_meta` counts up, the screen says she is speaking, and nothing
    // comes out of the speaker. `resume()` is idempotent and a no-op on an
    // already-running context, so it is cheaper to call than to reason about.
    if (this.context.state === "suspended") void this.context.resume();
    return this.context;
  }

  push(pcm: ArrayBuffer): void {
    const context = this.ensure();
    const samples = new Int16Array(pcm);
    const buffer = context.createBuffer(1, samples.length, BINARY_SAMPLE_RATE_HZ);
    const channel = buffer.getChannelData(0);
    for (let i = 0; i < samples.length; i += 1) channel[i] = samples[i]! / 32768;

    const source = context.createBufferSource();
    source.buffer = buffer;
    source.connect(context.destination);
    // Never schedule in the past: a late frame plays now rather than being
    // dropped, which is a click instead of a hole.
    this.playAt = Math.max(this.playAt, context.currentTime);
    source.start(this.playAt);
    this.playAt += buffer.duration;
    this.sources.push(source);
    source.onended = () => {
      this.sources = this.sources.filter((s) => s !== source);
    };
  }

  /** §25.3's barge-in: everything not yet heard stops being going to be heard. */
  drop(): void {
    for (const source of this.sources) {
      try {
        source.stop();
      } catch {
        /* already ended */
      }
    }
    this.sources = [];
    this.playAt = this.context?.currentTime ?? 0;
  }

  async close(): Promise<void> {
    this.drop();
    await this.context?.close();
    this.context = null;
  }
}

export class CallSocket {
  private ws: WebSocket | null = null;
  private recorder: VoiceRecorder | null = null;
  private player = new PcmPlayer();
  private closedByUs = false;
  private attempt = 0;
  private openedAt = 0;
  private resumeToken: string | null = null;
  /** §25.3: "mute is client-hard" — the frames never leave, not a server flag. */
  private muted = false;

  constructor(
    private readonly conversationId: string,
    private readonly locale: string,
    private readonly handlers: CallHandlers,
  ) {}

  async connect(): Promise<void> {
    const grant = await apiCall<CallGrant>("/v1/call/session", {
      method: "POST",
      body: JSON.stringify({ conversation_id: this.conversationId, locale: this.locale }),
    });
    if (!grant.ok) {
      // §33.5's flag, CC-010's locale ruling and an exhausted §7.3 pool all
      // arrive here. The screen renders each as a reason, never as a failure.
      this.handlers.onRefused(grant.error);
      return;
    }
    this.handlers.onGrant(grant.data);
    this.open(grant.data);
  }

  private open(grant: CallGrant): void {
    const ws = new WebSocket(grant.ws_url);
    ws.binaryType = "arraybuffer";
    this.ws = ws;
    this.openedAt = this.openedAt || Date.now();

    ws.onopen = () => {
      ws.send(
        frame("session.start", {
          ticket: grant.ticket,
          conversation_id: this.conversationId,
          locale: this.locale,
          resume_token: this.resumeToken,
        }),
      );
    };

    ws.onmessage = (message) => {
      if (message.data instanceof ArrayBuffer) {
        // Her audio plays whether or not the USER is muted. §25.3's mute is
        // the microphone control — "mute · end · speaker" — and silencing her
        // as well would make it a control nobody could use for its actual
        // purpose (listening while a room is noisy). The speaker is the other
        // button.
        this.player.push(message.data);
        return;
      }
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
        void this.startMic();
      }
      if (event.type === "barge_in") {
        // The server has already stopped synthesising; this drops what the
        // browser had buffered ahead of the speaker.
        this.player.drop();
      }
      if (event.type === "handoff.to_text") {
        // The call is over as a call. Stop capturing immediately rather than
        // waiting for the screen to unmount — a microphone that stays live
        // through a handoff is a microphone nobody thinks is on.
        void this.stopMic();
      }
      this.handlers.onEvent(event);
    };

    ws.onclose = () => {
      void this.stopMic();
      if (this.closedByUs) return;
      this.ws = null;
      const withinWindow = Date.now() - this.openedAt < RESUME_WINDOW_S * 1000;
      this.handlers.onClosed();
      if (!withinWindow || this.attempt >= RETRY_DELAYS_MS.length) return;
      const delay = RETRY_DELAYS_MS[Math.min(this.attempt, RETRY_DELAYS_MS.length - 1)]!;
      this.attempt += 1;
      window.setTimeout(() => void this.connect(), delay);
    };
  }

  private async startMic(): Promise<void> {
    if (this.recorder) return;
    // `VoiceRecorder` already emits §34.6's framed bytes — 8-byte header
    // attached, 16 kHz mono s16le — because that is the one capture path in
    // the app and the voice notes use it too. Re-framing here would have put
    // two headers on every frame, which the server reads as a sample count
    // that does not divide by two.
    const recorder = new VoiceRecorder({ onFrame: (frame) => this.sendAudio(frame) });
    this.recorder = recorder;
    try {
      await recorder.start();
    } catch {
      // §30.1: a denied microphone leaves text working. The screen shows the
      // recovery path; the call itself cannot continue without input, so the
      // server's silence detector will hand off on its own.
      this.recorder = null;
    }
  }

  private async stopMic(): Promise<void> {
    const recorder = this.recorder;
    this.recorder = null;
    await recorder?.stop();
  }

  private sendAudio(framed: ArrayBuffer): void {
    // **Client-hard mute (§25.3).** The frames are not flagged, not zeroed and
    // not ignored server-side: they are never sent. A mute the server could
    // fail to honour is a mute a user cannot trust, and this is the one control
    // on the screen where that distinction is the whole feature.
    if (this.muted) return;
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    this.ws.send(framed);
  }

  /** §25.3's mute: MY microphone, and nothing else. */
  setMuted(muted: boolean): void {
    this.muted = muted;
  }

  close(): void {
    this.closedByUs = true;
    this.ws?.send(frame("session.end", {}));
    this.ws?.close();
    this.ws = null;
    void this.stopMic();
    void this.player.close();
  }
}
