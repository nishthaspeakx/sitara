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

import { ICON_STROKE, cn, focusRing, motionStandard, touchTarget } from "./_util";

export type VoiceNoteMode = "recording" | "idle" | "playing";
export type TranscriptStatus = "ready" | "pending" | "failed" | "none";

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
  transcriptStatus?: TranscriptStatus;
  /** Shown when transcriptStatus === "ready". */
  transcript?: string;
  /** In-locale expiry line for the stored original (§33.1, 30d default). */
  expiresOn?: string;
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
  transcriptStatus = "none",
  transcript,
  expiresOn,
  className,
}: VoiceNoteBubbleProps) {
  const t = useTranslations();
  const recording = mode === "recording";

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={recording ? onStopRecording : onTogglePlay}
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
          ) : mode === "playing" ? (
            <Pause aria-hidden="true" strokeWidth={ICON_STROKE} />
          ) : (
            <Play aria-hidden="true" strokeWidth={ICON_STROKE} />
          )}
        </button>

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

        {!recording && onCycleSpeed ? (
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

      {expiresOn ? (
        <p className="text-caption text-ink-muted">
          {t("ui.audio.expires_on", { date: expiresOn })}
        </p>
      ) : null}
    </div>
  );
}
