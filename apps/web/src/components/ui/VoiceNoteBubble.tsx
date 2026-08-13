"use client";

/**
 * VoiceNoteBubble — §24.3 / §25.4. States: record · play · speed · transcript.
 *
 * §33.1 / §6.4, and this is the part that must not be got wrong: the ORIGINAL
 * audio is stored encrypted for 30 days by default, and the bubble tells the
 * user when it expires rather than leaving it implicit. Call audio is NEVER
 * stored, so this component is for notes only and has no call variant.
 *
 * `transcriptStatus` mirrors the §6.4 message field; "pending" and "failed" are
 * shown honestly instead of an empty transcript.
 */

import { Mic, Pause, Play, Square } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import type { TranscriptStatus } from "@sitara/schemas";

import { ICON_STROKE, cn, focusRing, motionStandard, touchTarget } from "./_util";

export type VoiceNoteMode = "recording" | "idle" | "playing";

/**
 * §6.4's `messages.transcript_status`, from `@sitara/schemas`.
 *
 * This file used to declare its own — `"ready" | "pending" | "failed" | "none"`
 * — while `services/api`'s message store wrote `"not_applicable"` and
 * `"text_only"`. Neither had ever crossed the wire, so nothing failed: the same
 * invisibility that hid the confidence states, the presence states and the
 * memory types until the first screen rendered one. M9's bubble is that first
 * screen, and the compiler caught it the moment the two met.
 */
export type { TranscriptStatus } from "@sitara/schemas";

export const PLAYBACK_SPEEDS = [1, 1.5, 2] as const;
export type PlaybackSpeed = (typeof PLAYBACK_SPEEDS)[number];

export interface VoiceNoteBubbleProps {
  mode: VoiceNoteMode;
  /** Formatted by the caller, e.g. "0:12". */
  duration: string;
  /** 0–1 waveform levels. */
  levels?: number[];
  speed?: PlaybackSpeed;
  onCycleSpeed?: () => void;
  onTogglePlay?: () => void;
  onStopRecording?: () => void;
  /** `not_applicable` is a typed message and renders no transcript line. */
  transcriptStatus?: TranscriptStatus;
  /** Shown when transcriptStatus === "ready". */
  transcript?: string;
  /** In-locale expiry line for the stored original (§33.1, 30d default). */
  expiresOn?: string;
  /**
   * The ORIGINAL recording (§25.4). Absent means there is nothing to play —
   * §33.1's ephemeral mode, or a note whose thirty days are up — and the
   * component then renders NO play control rather than a dead one.
   *
   * For a user's note this is always their own audio. §25.4's promise is that
   * it is "never a TTS reconstruction", and the caller enforces that by having
   * no field on a user message that could carry a synthesised asset id.
   */
  src?: string;
  /**
   * §33.1: when playback is gone, the bubble "shows the transcript with a
   * 'voice input' marker". An i18n key, because it is copy (§2.4).
   */
  markerKey?: string;
  className?: string;
}

const DEFAULT_LEVELS = [0.4, 0.8, 0.5, 0.95, 0.6, 0.3, 0.7, 0.55, 0.85, 0.45];

export function VoiceNoteBubble({
  mode,
  duration,
  levels = DEFAULT_LEVELS,
  speed = 1,
  onCycleSpeed,
  onTogglePlay,
  onStopRecording,
  transcriptStatus = "not_applicable",
  transcript,
  expiresOn,
  src,
  markerKey,
  className,
}: VoiceNoteBubbleProps) {
  const t = useTranslations();
  const recording = mode === "recording";
  const audio = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);

  // The speed control is §28.3's 1/1.5/2×, and it must reach the element or it
  // is a chip that changes a number and nothing else.
  useEffect(() => {
    if (audio.current) audio.current.playbackRate = speed;
  }, [speed]);

  function toggle() {
    onTogglePlay?.();
    const element = audio.current;
    if (!element) return;
    if (element.paused) void element.play();
    else element.pause();
  }

  // No `src` means no control at all. §33.1 has the bubble "honestly drop
  // playback of expired/deleted audio" — a disabled play button still says
  // "there is a recording here", which is the thing that is no longer true.
  const playable = Boolean(src) && !recording;

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      {src ? (
        <audio
          ref={audio}
          src={src}
          preload="none"
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onEnded={() => setPlaying(false)}
        />
      ) : null}

      <div className="flex items-center gap-3">
        {recording || playable ? (
        <button
          type="button"
          onClick={recording ? onStopRecording : toggle}
          aria-label={t(
            recording ? "ui.audio.stop_recording" : mode === "playing" ? "ui.audio.pause" : "ui.audio.play",
          )}
          className={cn(
            "inline-flex shrink-0 items-center justify-center rounded-portrait border border-border-strong bg-surface text-ink-primary",
            touchTarget,
            motionStandard,
            focusRing,
          )}
        >
          {recording ? (
            <Square aria-hidden="true" strokeWidth={ICON_STROKE} />
          ) : playing || mode === "playing" ? (
            <Pause aria-hidden="true" strokeWidth={ICON_STROKE} />
          ) : (
            <Play aria-hidden="true" strokeWidth={ICON_STROKE} />
          )}
        </button>
        ) : null}

        <div aria-hidden="true" className="flex h-6 flex-1 items-end gap-1">
          {levels.map((level, i) => (
            <span
              key={i}
              style={{ height: `${Math.round(level * 100)}%` }}
              className={cn(
                "w-1 rounded-chip bg-gold-soft",
                recording &&
                  "motion-safe:animate-pulse motion-reduce:animate-none motion-off:animate-none",
              )}
            />
          ))}
        </div>

        <span className="shrink-0 text-caption text-ink-muted tabular-nums">{duration}</span>

        {playable && onCycleSpeed ? (
          <button
            type="button"
            onClick={onCycleSpeed}
            aria-label={t("ui.audio.speed")}
            className={cn(
              "shrink-0 rounded-chip border border-border-subtle px-2 py-1 text-caption text-ink-primary tabular-nums",
              motionStandard,
              focusRing,
            )}
          >
            {t("ui.audio.speed_value", { speed })}
          </button>
        ) : null}

        {recording ? (
          <Mic aria-hidden="true" strokeWidth={ICON_STROKE} className="shrink-0 text-ink-muted" />
        ) : null}
      </div>

      {transcriptStatus === "ready" && transcript ? (
        <p className="max-w-reading text-caption text-ink-muted">{transcript}</p>
      ) : null}
      {transcriptStatus === "pending" ? (
        <p className="text-caption text-ink-muted">{t("ui.audio.transcript_pending")}</p>
      ) : null}
      {transcriptStatus === "failed" ? (
        <p className="text-caption text-ink-muted">{t("ui.audio.transcript_failed")}</p>
      ) : null}

      {markerKey ? (
        <p className="text-caption text-ink-muted" data-testid="voice-input-marker">
          {t(markerKey)}
        </p>
      ) : null}

      {expiresOn ? (
        <p className="text-caption text-ink-muted">
          {t("ui.audio.expires_on", { date: expiresOn })}
        </p>
      ) : null}
    </div>
  );
}
