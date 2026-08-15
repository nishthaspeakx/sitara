"use client";

/**
 * The composer — text and §25.4's voice notes (M9).
 *
 * §30.1's rule shapes the layout: **text always works**, so the field is never
 * replaced by the mic. The two sit side by side and the mic is the affordance
 * that can fail (permission, vendor, network) without taking the composer with
 * it. `VOICE_NOTES_ENABLED` remains as an operator kill switch.
 *
 * The recording STATE lives in `lib/voice-note.ts` and the microphone in
 * `lib/voice-recorder.ts`; this component owns neither. What is hard about
 * hold-to-record — a 40ms brush, a release while locked, an overshot cancel
 * gesture — is testable there without a browser.
 *
 * The quote strip above the field is §25.4's swipe-to-reply, and it is not
 * decoration: the id travels with the turn and the pipeline reads the quoted
 * message explicitly.
 */

import { Mic, MicOff, SendHorizontal, Square, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";

import { IconButton } from "@/components/ui";
import { ICON_STROKE, cn, focusRing, touchTarget } from "@/components/ui/_util";
import { VOICE_NOTES_ENABLED } from "@/lib/features";
import { formatDuration, type VoiceNoteState } from "@/lib/voice-note";

export function Composer({
  quoting,
  onClearQuote,
  onSend,
  disabled = false,
  voice,
  onVoicePress,
  onVoiceRelease,
  onVoiceStop,
  micDenied = false,
  onOpenMicHelp,
}: {
  /** The text of the message being replied to, already the user's own words. */
  quoting?: string;
  onClearQuote?: () => void;
  onSend: (text: string) => void;
  disabled?: boolean;
  /** §25.4's recording state. Absent means the screen has not wired voice. */
  voice?: VoiceNoteState;
  onVoicePress?: () => void;
  onVoiceRelease?: () => void;
  onVoiceStop?: () => void;
  micDenied?: boolean;
  onOpenMicHelp?: () => void;
}) {
  const t = useTranslations();
  const [value, setValue] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    const text = value.trim();
    if (!text) return;
    onSend(text);
    setValue("");
  }

  return (
    <form
      onSubmit={submit}
      data-testid="composer"
      className="flex flex-col gap-2 border-t border-border-subtle bg-surface px-4 py-3 pb-safe-min"
    >
      {quoting ? (
        <div
          data-testid="quote-strip"
          className="flex items-center gap-2 rounded-card border-s-2 border-gold bg-surface-sunken px-3 py-2"
        >
          <div className="flex min-w-0 flex-col">
            <span className="text-caption text-ink-muted">{t("ui.ask.quoting")}</span>
            <span className="truncate text-caption text-ink-primary">{quoting}</span>
          </div>
          <button
            type="button"
            onClick={onClearQuote}
            aria-label={t("ui.ask.quote_clear")}
            className={cn("ms-auto shrink-0 rounded-chip p-1 text-ink-muted", focusRing)}
          >
            <X aria-hidden="true" strokeWidth={ICON_STROKE} className="h-4 w-4" />
          </button>
        </div>
      ) : null}

      {VOICE_NOTES_ENABLED && voice && voice.phase !== "idle" ? (
        <p aria-live="polite" data-testid="voice-elapsed" className="text-caption text-ink-muted">
          {voice.phase === "cancelling"
            ? t("ui.voice.slide_to_cancel")
            : voice.phase === "locked"
              ? t("ui.voice.locked")
              : formatDuration(voice.elapsedMs)}
        </p>
      ) : null}

      <div className="flex items-end gap-2">
        <label className="sr-only" htmlFor="ask-composer">
          {t("ui.ask.placeholder")}
        </label>
        <input
          id="ask-composer"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={t("ui.ask.placeholder")}
          autoComplete="off"
          className={cn(
            "min-w-0 flex-1 rounded-chip border border-border-subtle bg-bg-canvas px-3 text-body text-ink-primary placeholder:text-ink-muted",
            touchTarget,
            focusRing,
          )}
        />
        {/* §28.3's entry for a voice note is "mic hold/lock in composer" — a
            button beside the field. NOT `VoiceBar`: that is §25.3's call
            component (button + status label + waveform, sized to own a screen),
            and inlining it here leaked its status text into the composer row.
            The recording state is announced above instead, on one live region. */}
        {VOICE_NOTES_ENABLED && voice ? (
          <IconButton
            labelKey={
              micDenied
                ? "ui.voice.mic_denied"
                : voice.phase === "locked"
                  ? "ui.audio.stop_recording"
                  : "ui.voice.idle"
            }
            onClick={micDenied ? onOpenMicHelp : voice.phase === "locked" ? onVoiceStop : undefined}
            onPointerDown={micDenied || voice.phase === "locked" ? undefined : onVoicePress}
            onPointerUp={micDenied || voice.phase === "locked" ? undefined : onVoiceRelease}
            icon={
              micDenied ? (
                <MicOff aria-hidden="true" strokeWidth={ICON_STROKE} />
              ) : voice.phase === "locked" ? (
                <Square aria-hidden="true" strokeWidth={ICON_STROKE} />
              ) : (
                <Mic aria-hidden="true" strokeWidth={ICON_STROKE} />
              )
            }
          />
        ) : null}
        <IconButton
          type="submit"
          labelKey="ui.ask.send"
          disabled={disabled || !value.trim()}
          icon={<SendHorizontal aria-hidden="true" strokeWidth={ICON_STROKE} />}
        />
      </div>
    </form>
  );
}
