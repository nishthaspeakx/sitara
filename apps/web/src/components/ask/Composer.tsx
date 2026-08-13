"use client";

/**
 * The composer. Text only — §25.4's voice notes are dark until M9.
 *
 * `VOICE_NOTES_ENABLED` gates the mic affordance rather than the code being
 * absent: `VoiceBar` and `VoiceNoteBubble` are built, storied and screenshotted
 * in the §24.3 library. What is missing is §33.1's encrypted storage of the
 * ORIGINAL recording, and without it §25.4's "replay plays the user's original
 * recording, never a TTS reconstruction" cannot be honoured. A mic button
 * before that is a promise the app cannot keep.
 *
 * The quote strip above the field is §25.4's swipe-to-reply, and it is not
 * decoration: the id travels with the turn and the pipeline reads the quoted
 * message explicitly.
 */

import { SendHorizontal, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";

import { IconButton } from "@/components/ui";
import { ICON_STROKE, cn, focusRing, touchTarget } from "@/components/ui/_util";
import { VOICE_NOTES_ENABLED } from "@/lib/features";

export function Composer({
  quoting,
  onClearQuote,
  onSend,
  disabled = false,
}: {
  /** The text of the message being replied to, already the user's own words. */
  quoting?: string;
  onClearQuote?: () => void;
  onSend: (text: string) => void;
  disabled?: boolean;
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
      className="flex flex-col gap-2 border-t border-border-subtle bg-surface px-4 py-3 pb-[max(env(safe-area-inset-bottom),0.75rem)]"
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
        {/* M9 mounts the VoiceBar here. Left as a comment rather than a
            commented-out component: dead JSX rots, and the library component
            already carries its own states and baselines. */}
        {VOICE_NOTES_ENABLED ? null : null}
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
