"use client";

/**
 * CallControls — §24.3 / §25.3 / S19. mute · end · speaker, plus the plan chip.
 *
 * §29.2 acceptance for S19: end-call is EXPLICIT — it is the one control that
 * is always full size, always labelled, and never hidden behind an overflow.
 * All controls are ≥48px per the S19 a11y line, above the §24.2 44px floor.
 *
 * §33.1: call audio is never stored, and the privacy line says so on the call
 * screen rather than in a policy page.
 */

import { Captions, Mic, MicOff, PhoneOff, Volume2, VolumeX } from "lucide-react";
import { useTranslations } from "next-intl";

import { IconButton } from "./IconButton";
import { ICON_STROKE, cn, focusRing, motionStandard } from "./_util";

export interface CallControlsProps {
  muted: boolean;
  onToggleMute: () => void;
  speakerOn: boolean;
  onToggleSpeaker: () => void;
  captionsOn?: boolean;
  onToggleCaptions?: () => void;
  onEnd: () => void;
  /** Minutes remaining; the meter appears from 20% remaining (§S19). */
  minutesLeft?: number;
  minutesTotal?: number;
  onOpenPlan?: () => void;
  className?: string;
}

export function CallControls({
  muted,
  onToggleMute,
  speakerOn,
  onToggleSpeaker,
  captionsOn,
  onToggleCaptions,
  onEnd,
  minutesLeft,
  minutesTotal,
  onOpenPlan,
  className,
}: CallControlsProps) {
  const t = useTranslations();
  const showMeter =
    typeof minutesLeft === "number" &&
    typeof minutesTotal === "number" &&
    minutesTotal > 0 &&
    minutesLeft / minutesTotal <= 0.2;

  return (
    <div
      className={cn(
        // safe-area padding for the iOS home bar (§29.3)
        "flex flex-col items-center gap-3 pb-[env(safe-area-inset-bottom)]",
        className,
      )}
    >
      {showMeter ? (
        <button
          type="button"
          onClick={onOpenPlan}
          className={cn(
            "rounded-chip border border-border-subtle bg-surface px-3 py-1 text-caption text-ink-primary tabular-nums",
            motionStandard,
            focusRing,
          )}
        >
          {t("ui.call.minutes_left", { minutes: minutesLeft })}
        </button>
      ) : null}

      <div className="flex items-center gap-4">
        <IconButton
          variant="outline"
          labelKey={muted ? "ui.call.unmute" : "ui.call.mute"}
          pressed={muted}
          onClick={onToggleMute}
          className="h-control-height w-control-height"
          icon={
            muted ? (
              <MicOff strokeWidth={ICON_STROKE} />
            ) : (
              <Mic strokeWidth={ICON_STROKE} />
            )
          }
        />

        {/* end-call is explicit: largest target, always labelled in text too */}
        <button
          type="button"
          onClick={onEnd}
          className={cn(
            "inline-flex flex-col items-center justify-center gap-1 rounded-portrait border border-border-strong bg-feedback-danger-strong px-4 py-3 text-on-brand",
            motionStandard,
            focusRing,
          )}
        >
          <PhoneOff aria-hidden="true" strokeWidth={ICON_STROKE} />
          <span className="text-caption">{t("ui.call.end")}</span>
        </button>

        <IconButton
          variant="outline"
          labelKey={speakerOn ? "ui.call.speaker_off" : "ui.call.speaker_on"}
          pressed={speakerOn}
          onClick={onToggleSpeaker}
          className="h-control-height w-control-height"
          icon={
            speakerOn ? (
              <Volume2 strokeWidth={ICON_STROKE} />
            ) : (
              <VolumeX strokeWidth={ICON_STROKE} />
            )
          }
        />

        {onToggleCaptions ? (
          <IconButton
            variant="outline"
            labelKey="ui.call.captions"
            pressed={captionsOn}
            onClick={onToggleCaptions}
            className="h-control-height w-control-height"
            icon={<Captions strokeWidth={ICON_STROKE} />}
          />
        ) : null}
      </div>

      <p className="text-caption text-ink-muted">{t("ui.call.privacy_line")}</p>
    </div>
  );
}
