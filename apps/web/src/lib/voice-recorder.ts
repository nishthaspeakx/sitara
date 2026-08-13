"use client";

/**
 * Microphone → §34.6's binary frame. The only file that touches `getUserMedia`.
 *
 * §34.6 fixes the wire format: 16 kHz mono PCM s16le, each chunk prefixed with
 * an 8-byte header (4-byte big-endian monotonic seq + 4-byte flags). Everything
 * here exists to produce exactly that and nothing else.
 *
 * **Why not `MediaRecorder`.** It is the obvious API and it is the wrong one:
 * it emits a container (webm/opus on Chrome, mp4/aac on Safari) chosen by the
 * browser, so the server would receive a different codec per browser and §33.1's
 * "the ORIGINAL recording" would mean a different thing on each. Worse, §25.4's
 * replay promise then depends on decoding whatever that browser chose, thirty
 * days later, possibly in a different browser. An AudioWorklet gives raw
 * samples, so the bytes stored are the bytes captured and every client agrees.
 *
 * **The seq is per RECORDING, not per socket.** It resets at each
 * `speech_start`, because the server reassembles one note at a time and a gap
 * fails that note (see `services/realtime`'s `Recording`).
 */

import { BINARY_SAMPLE_RATE_HZ } from "@sitara/schemas";

/** Emitted at ~85ms of audio, which keeps frames small without flooding. */
const SAMPLES_PER_FRAME = 1_365;

const WORKLET = `
class PcmTap extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    // A disconnected mic gives an empty input rather than silence. Returning
    // true keeps the node alive so a device change mid-note does not kill it.
    if (channel && channel.length) this.port.postMessage(channel.slice());
    return true;
  }
}
registerProcessor('pcm-tap', PcmTap);
`;

export interface VoiceRecorderHandlers {
  /** One §34.6 binary frame, header already attached. */
  onFrame: (frame: ArrayBuffer) => void;
  /** 0–1 levels for the waveform. Decorative — the state is announced in words. */
  onLevel?: (level: number) => void;
  /** The mic was refused. §30.1: text always works, so this is not fatal. */
  onDenied?: () => void;
}

export class VoiceRecorder {
  private context: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private node: AudioWorkletNode | null = null;
  private pending: Float32Array[] = [];
  private pendingLength = 0;
  private seq = 0;

  constructor(private readonly handlers: VoiceRecorderHandlers) {}

  /** True once the mic is live and frames are flowing. */
  get active(): boolean {
    return this.node !== null;
  }

  async start(): Promise<boolean> {
    if (this.node) return true;
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          // Left on deliberately: a voice note is a phone in a kitchen, and
          // §3.4's corpus is scored on intelligibility, not fidelity.
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
    } catch {
      // Browsers will not re-prompt, so §30.1's recovery path is an ⓘ that
      // explains how to re-enable — `VoiceBar` already renders it.
      this.handlers.onDenied?.();
      return false;
    }

    // Ask for the wire's rate directly. Where the hardware refuses, the
    // resample below carries it — Safari in particular pins 44.1/48k.
    this.context = new AudioContext({ sampleRate: BINARY_SAMPLE_RATE_HZ });
    await this.context.audioWorklet.addModule(
      URL.createObjectURL(new Blob([WORKLET], { type: "application/javascript" })),
    );

    this.seq = 0;
    this.pending = [];
    this.pendingLength = 0;

    const source = this.context.createMediaStreamSource(this.stream);
    this.node = new AudioWorkletNode(this.context, "pcm-tap");
    this.node.port.onmessage = (event) => this.accept(event.data as Float32Array);
    source.connect(this.node);
    // NOT connected to `destination`: routing the mic to the speakers is a
    // feedback loop, and the worklet pulls regardless.
    return true;
  }

  /** Flush whatever is buffered and release the microphone. */
  async stop(): Promise<void> {
    if (this.pendingLength > 0) this.emit(this.drain());
    this.node?.port.close();
    this.node?.disconnect();
    this.node = null;
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
    await this.context?.close();
    this.context = null;
  }

  /** Release the microphone WITHOUT flushing — §28.3's cancel-slide. */
  async discard(): Promise<void> {
    this.pending = [];
    this.pendingLength = 0;
    await this.stop();
  }

  private accept(samples: Float32Array): void {
    if (this.handlers.onLevel) {
      let peak = 0;
      for (const sample of samples) peak = Math.max(peak, Math.abs(sample));
      this.handlers.onLevel(Math.min(1, peak));
    }
    this.pending.push(samples);
    this.pendingLength += samples.length;
    while (this.pendingLength >= SAMPLES_PER_FRAME) {
      this.emit(this.take(SAMPLES_PER_FRAME));
    }
  }

  private take(count: number): Float32Array {
    const out = new Float32Array(count);
    let filled = 0;
    while (filled < count) {
      const head = this.pending[0];
      // `pendingLength` is the invariant that makes this loop terminate, so an
      // empty queue here would be a bookkeeping bug, not a runtime condition.
      if (head === undefined) break;
      const need = count - filled;
      if (head.length <= need) {
        out.set(head, filled);
        filled += head.length;
        this.pending.shift();
      } else {
        out.set(head.subarray(0, need), filled);
        this.pending[0] = head.subarray(need);
        filled += need;
      }
    }
    this.pendingLength -= count;
    return out;
  }

  private drain(): Float32Array {
    return this.take(this.pendingLength);
  }

  private emit(samples: Float32Array): void {
    this.handlers.onFrame(frameFrom(samples, this.seq++));
  }
}

/**
 * Float32 [-1, 1] → s16le, behind §34.6's 8-byte header.
 *
 * Clamping before scaling matters: a sample slightly outside the range (which
 * the Web Audio spec permits) wraps to the opposite sign in a raw cast, so a
 * loud syllable becomes an audible click rather than a clipped one.
 */
export function frameFrom(samples: Float32Array, seq: number, flags = 0): ArrayBuffer {
  const buffer = new ArrayBuffer(8 + samples.length * 2);
  const view = new DataView(buffer);
  view.setUint32(0, seq, false); // big-endian, per §34.6
  view.setUint32(4, flags, false);
  for (let i = 0; i < samples.length; i += 1) {
    const clamped = Math.max(-1, Math.min(1, samples[i] ?? 0));
    view.setInt16(8 + i * 2, Math.round(clamped * 0x7fff), true); // s16LE
  }
  return buffer;
}
