"use client";

/**
 * §25.4's hold-to-record, joined to the microphone and the socket.
 *
 * The three parts are deliberately separate and only meet here:
 *   `voice-note.ts`      the state machine — pure, tested with no browser
 *   `voice-recorder.ts`  the microphone — the only file touching getUserMedia
 *   `chat-socket.ts`     §34.6's frames
 *
 * This hook is the join, and it owns one ordering that is easy to get wrong:
 * **the socket bracket opens before the microphone does.** `VoiceRecorder.start()`
 * is async, and the AudioWorklet begins emitting the moment it is connected —
 * inside that promise, before any `.then()` here runs. Opening the bracket
 * afterwards lets frames arrive ahead of `vad.state: speech_start`; the server
 * refuses them, and the refusal is not the damage — the recorder's sequence has
 * already advanced, so the note then dies on a gap that was really a race. It
 * reproduced as a note that simply never arrived.
 *
 * The BUBBLE, by contrast, is created once audio is actually flowing, keyed by
 * the same id, so every frame belongs to a message the thread is already
 * drawing rather than the transcript inventing one seconds later.
 *
 * **A cancel discards locally even if the socket is gone.** `cancelRecording`
 * returning false is not a failure the user needs to hear about: the recorder's
 * own buffer is dropped either way, and there is nothing to cancel on a dead
 * socket. §28.3's promise is about what leaves the device.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import type { ChatSocket } from "./chat-socket";
import {
  IDLE_VOICE_NOTE,
  isRecording,
  voiceNoteReducer,
  type VoiceNoteAction,
  type VoiceNoteState,
} from "./voice-note";
import { VoiceRecorder } from "./voice-recorder";

/** How often the elapsed counter advances. Fine enough to read, cheap enough. */
const TICK_MS = 100;

export interface UseVoiceNote {
  state: VoiceNoteState;
  micDenied: boolean;
  /** 0–1 levels for the waveform. Decorative; the state is announced in words. */
  levels: number[];
  press: () => void;
  move: (dx: number, dy: number) => void;
  release: () => void;
  stop: () => void;
  cancel: () => void;
}

export function useVoiceNote({
  socket,
  mintId,
  onSpeak,
  quotedId,
}: {
  socket: { current: ChatSocket | null };
  mintId: () => string;
  /** Creates the bubble the frames belong to. */
  onSpeak: (id: string, durationMs: number, quotedId?: string) => void;
  quotedId?: string;
}): UseVoiceNote {
  const [state, setState] = useState<VoiceNoteState>(IDLE_VOICE_NOTE);
  const [micDenied, setMicDenied] = useState(false);
  const [levels, setLevels] = useState<number[]>([]);

  const recorder = useRef<VoiceRecorder | null>(null);
  const startedAt = useRef(0);
  // The machine is the source of truth for the timer and the release handler,
  // both of which run outside React's render — a ref keeps them reading the
  // value that exists NOW rather than the one their closure captured.
  const current = useRef(state);
  current.current = state;

  const apply = useCallback((action: VoiceNoteAction) => {
    setState((previous) => {
      const next = voiceNoteReducer(previous, action, startedAt.current);
      current.current = next;
      return next;
    });
  }, []);

  // The elapsed clock. `Date.now()` is read HERE and passed in, so the reducer
  // stays pure and its tests stay clock-free.
  //
  // Keyed on `phase` ALONE, deliberately: every tick changes `elapsedMs`, so a
  // dependency on the whole state would tear the interval down and rebuild it
  // ten times a second. The effect body reads phase and nothing else.
  useEffect(() => {
    if (!isRecording(current.current)) return;
    const timer = window.setInterval(() => apply({ type: "tick", at: Date.now() }), TICK_MS);
    return () => window.clearInterval(timer);
  }, [state.phase, apply]);

  // The cap fires inside the reducer, so the recorder has to be told separately.
  useEffect(() => {
    if (state.phase === "uploading" && recorder.current?.active) {
      const id = state.clientMessageId;
      void recorder.current.stop().then(() => {
        if (id) socket.current?.finishRecording(id);
      });
    }
  }, [state.phase, state.clientMessageId, socket]);

  const press = useCallback(() => {
    const id = mintId();

    // **The bracket opens BEFORE the microphone.**
    //
    // `VoiceRecorder.start()` is async (getUserMedia, then an AudioWorklet
    // module fetch), and the worklet begins emitting the moment it is
    // connected — which is inside that promise, before any `.then()` of ours
    // runs. Opening the bracket afterwards leaves a window in which frames
    // arrive with no `vad.state` in front of them. The server refuses those
    // (correctly), and the refusal is not the damage: the recorder's sequence
    // has already advanced, so the FIRST accepted frame is seq 1 where the
    // server expects 0, and the note dies on a gap that was really a race.
    // It reproduced as a note that simply never arrived.
    const bracketed = socket.current?.startRecording(id, quotedId) ?? false;

    const client = new VoiceRecorder({
      onFrame: (frame) => socket.current?.sendAudio(frame),
      onLevel: (level) =>
        setLevels((previous) => [...previous.slice(-11), Math.max(0.08, level)]),
      onDenied: () => {
        // §30.1: text always works, so this is not fatal and not an error
        // envelope. `VoiceBar` keeps the affordance visible with an ⓘ, because
        // browsers will not re-prompt.
        setMicDenied(true);
        setState(IDLE_VOICE_NOTE);
      },
    });
    recorder.current = client;

    void client.start().then((live) => {
      if (!live) {
        // A denied microphone must not leave a bracket open on the server.
        if (bracketed) socket.current?.cancelRecording(id);
        return;
      }
      // The clock starts when AUDIO does, not when the finger landed: mic
      // startup is 50–200ms and counting it would inflate every duration and
      // let a sub-threshold tap past the 500ms guard.
      startedAt.current = Date.now();
      onSpeak(id, 0, quotedId);
      apply({ type: "press", id, at: startedAt.current, quotedId });
    });
  }, [apply, mintId, onSpeak, quotedId, socket]);

  const move = useCallback((dx: number, dy: number) => apply({ type: "move", dx, dy }), [apply]);

  const finish = useCallback(async () => {
    const id = current.current.clientMessageId;
    await recorder.current?.stop();
    recorder.current = null;
    setLevels([]);
    if (id) socket.current?.finishRecording(id);
  }, [socket]);

  const discard = useCallback(async () => {
    const id = current.current.clientMessageId;
    await recorder.current?.discard();
    recorder.current = null;
    setLevels([]);
    // Best-effort: a dead socket has nothing to cancel, and the buffer above
    // is already gone. §28.3's promise is about what leaves the device.
    if (id) socket.current?.cancelRecording(id);
  }, [socket]);

  const release = useCallback(() => {
    const before = current.current;
    apply({ type: "release" });
    // A release while LOCKED keeps recording — that is what the lock is for.
    if (before.phase === "locked") return;
    if (before.phase === "cancelling") return void discard();
    // Too short to be speech: the reducer discards it, and so must the mic.
    // The bubble is removed too, because nothing was sent.
    if (before.elapsedMs < 500) return void discard();
    void finish();
  }, [apply, discard, finish]);

  const stop = useCallback(() => {
    apply({ type: "stop" });
    void finish();
  }, [apply, finish]);

  const cancel = useCallback(() => {
    apply({ type: "cancel" });
    void discard();
  }, [apply, discard]);

  // A screen that unmounts mid-hold must not leave the microphone live.
  useEffect(() => () => void recorder.current?.discard(), []);

  return { state, micDenied, levels, press, move, release, stop, cancel };
}
