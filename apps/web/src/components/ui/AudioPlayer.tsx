"use client";

/**
 * AudioPlayer — §24.3 feedback. The morning-brief player on S14.
 *
 * §S14 a11y: the brief has a transcript, and it is a peer of the audio rather
 * than a hidden fallback — listening and reading are both first-class.
 *
 * Briefs are listen-only (§27); there is no download control and no speed ramp
 * beyond the §25.4 set, so this stays distinct from VoiceNoteBubble.
 */

import { Pause, Play, ScrollText } from "lucide-react";
import { useTranslations } from "next-intl";

import { ICON_STROKE, cn, focusRing, motionStandard, touchTarget } from "./_util";

export interface AudioPlayerProps {
  playing: boolean;
  onTogglePlay: () => void;
  /** 0–1. */
  progress: number;
  /** Formatted by the caller, e.g. "1:24". */
  elapsed: string;
  duration: string;
  onSeek?: (progress: number) => void;
  onOpenTranscript?: () => void;
  /** Shown when the brief could not be synthesised — the text brief still works. */
  unavailable?: boolean;
  className?: string;
}

export function AudioPlayer({
  playing,
  onTogglePlay,
  progress,
  elapsed,
  duration,
  onSeek,
  onOpenTranscript,
  unavailable = false,
  className,
}: AudioPlayerProps) {
  const t = useTranslations();

  if (unavailable) {
    return (
      <p
        className={cn(
          "rounded-card border border-border-subtle bg-surface-sunken p-3 text-caption text-ink-muted",
          className,
        )}
      >
        {t("ui.audio.unavailable")}
      </p>
    );
  }

  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-card border border-border-subtle bg-surface p-3",
        className,
      )}
    >
      <button
        type="button"
        onClick={onTogglePlay}
        aria-label={t(playing ? "ui.audio.pause" : "ui.audio.play")}
        className={cn(
          "inline-flex shrink-0 items-center justify-center rounded-portrait border border-border-strong bg-interactive-primary text-on-gold",
          touchTarget,
          motionStandard,
          focusRing,
        )}
      >
        {playing ? (
          <Pause aria-hidden="true" strokeWidth={ICON_STROKE} />
        ) : (
          <Play aria-hidden="true" strokeWidth={ICON_STROKE} />
        )}
      </button>

      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <input
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={progress}
          onChange={(e) => onSeek?.(Number(e.target.value))}
          aria-label={t("ui.audio.seek")}
          aria-valuetext={t("ui.audio.position", { elapsed, duration })}
          className={cn(
            "w-full appearance-none rounded-chip bg-interactive-disabled",
            "h-1 accent-[color:var(--color-interactive-primary)]",
            focusRing,
          )}
        />
        <div className="flex items-center justify-between text-caption text-ink-muted tabular-nums">
          <span>{elapsed}</span>
          <span>{duration}</span>
        </div>
      </div>

      {onOpenTranscript ? (
        <button
          type="button"
          onClick={onOpenTranscript}
          aria-label={t("ui.audio.transcript")}
          className={cn(
            "inline-flex shrink-0 items-center justify-center rounded-portrait text-ink-primary",
            touchTarget,
            focusRing,
          )}
        >
          <ScrollText aria-hidden="true" strokeWidth={ICON_STROKE} />
        </button>
      ) : null}
    </div>
  );
}
