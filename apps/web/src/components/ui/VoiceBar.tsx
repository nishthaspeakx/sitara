"use client";

/**
 * VoiceBar — §24.3 Sitara-specific. Push-to-talk with five states:
 * idle · listening · processing · speaking · error, a waveform, and a
 * barge-in tap while she is speaking (§25.3).
 *
 * §30.1: text always works. The bar therefore never becomes the only way
 * forward — when the mic is denied, the affordance stays visible with an ⓘ that
 * opens re-enable instructions, because browsers will not re-prompt.
 */

import { Mic, MicOff, Square, Info } from "lucide-react";
import { useTranslations } from "next-intl";

import { ICON_STROKE, cn, focusRing, motionStandard, touchTarget } from "./_util";

export const VOICE_STATES = ["idle", "listening", "processing", "speaking", "error"] as const;
export type VoiceState = (typeof VOICE_STATES)[number];

export interface VoiceBarProps {
  state: VoiceState;
  /** Press-and-hold to talk; a tap during `speaking` barges in. */
  onPress?: () => void;
  onRelease?: () => void;
  onBargeIn?: () => void;
  /** Mic permission was denied — §30.1's recovery path. */
  micDenied?: boolean;
  onOpenMicHelp?: () => void;
  /** 0–1 levels driving the waveform; static under reduced motion. */
  levels?: number[];
  className?: string;
}

const DEFAULT_LEVELS = [0.3, 0.7, 0.45, 0.9, 0.6, 0.35, 0.75, 0.5];

export function VoiceBar({
  state,
  onPress,
  onRelease,
  onBargeIn,
  micDenied = false,
  onOpenMicHelp,
  levels = DEFAULT_LEVELS,
  className,
}: VoiceBarProps) {
  const t = useTranslations();
  const speaking = state === "speaking";

  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-sheet border border-border-subtle bg-surface p-3",
        className,
      )}
    >
      <button
        type="button"
        disabled={micDenied || state === "processing"}
        onPointerDown={speaking ? undefined : onPress}
        onPointerUp={speaking ? undefined : onRelease}
        onClick={speaking ? onBargeIn : undefined}
        aria-label={t(speaking ? "ui.voice.barge_in" : `ui.voice.${state}`)}
        className={cn(
          "inline-flex shrink-0 items-center justify-center rounded-portrait border",
          touchTarget,
          motionStandard,
          focusRing,
          state === "listening"
            ? "bg-interactive-primary text-on-gold border-border-strong"
            : "bg-surface text-ink-primary border-border-strong",
          micDenied && "cursor-not-allowed text-ink-muted",
        )}
      >
        {micDenied ? (
          <MicOff aria-hidden="true" strokeWidth={ICON_STROKE} />
        ) : speaking ? (
          <Square aria-hidden="true" strokeWidth={ICON_STROKE} />
        ) : (
          <Mic aria-hidden="true" strokeWidth={ICON_STROKE} />
        )}
      </button>

      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <p aria-live="polite" className="text-caption text-ink-muted">
          {t(micDenied ? "ui.voice.mic_denied" : `ui.voice.${state}`)}
        </p>
        {/* the waveform is decorative; the state is announced in words above */}
        <div aria-hidden="true" className="flex h-6 items-end gap-1">
          {levels.map((level, i) => (
            <span
              key={i}
              style={{ height: `${Math.round(level * 100)}%` }}
              className={cn(
                "w-1 rounded-chip",
                state === "error" ? "bg-border-subtle" : "bg-gold-soft",
                state === "listening" &&
                  "motion-safe:animate-pulse motion-reduce:animate-none motion-off:animate-none",
              )}
            />
          ))}
        </div>
      </div>

      {micDenied ? (
        <button
          type="button"
          onClick={onOpenMicHelp}
          aria-label={t("ui.voice.mic_help")}
          className={cn(
            "inline-flex shrink-0 items-center justify-center rounded-portrait text-ink-primary",
            touchTarget,
            focusRing,
          )}
        >
          <Info aria-hidden="true" strokeWidth={ICON_STROKE} />
        </button>
      ) : null}
    </div>
  );
}
