"use client";

/**
 * ChatBubble — §24.3 Sitara-specific. User / Tara, fact-citation underlines,
 * audio variant.
 *
 * §29.5 (WhatsApp grammar): no repeated in-thread portrait per bubble — her
 * photo lives in the header, not on every message.
 *
 * §30.4: a cited span gets a gold underline and opens the TrustSheet. The
 * citation carries a `spanId` that is local to this message; **fact IDs stay
 * internal and never reach the DOM** — the caller resolves the span to a fact
 * privately and hands the TrustSheet finished sentences.
 */

import { useTranslations } from "next-intl";
import { Fragment, type ReactNode } from "react";

import { cn, focusRing, motionStandard } from "./_util";

export type ChatAuthor = "user" | "tara";

export interface CitedSpan {
  /** Message-local id. Never a fact ID (§30.4). */
  spanId: string;
  text: string;
}

export interface ChatBubbleProps {
  author: ChatAuthor;
  /** Plain segments and cited spans, in order. */
  content: Array<string | CitedSpan>;
  /** Opens the TrustSheet for a cited span. */
  onOpenTrust?: (spanId: string) => void;
  /** Formatted in-locale by the caller. */
  timestamp?: string;
  /** Renders the audio variant — a VoiceNoteBubble is passed in as children. */
  audio?: ReactNode;
  /** The message failed to send; retry lives with the bubble, not in a toast. */
  failed?: boolean;
  onRetry?: () => void;
  className?: string;
}

function isCited(part: string | CitedSpan): part is CitedSpan {
  return typeof part !== "string";
}

export function ChatBubble({
  author,
  content,
  onOpenTrust,
  timestamp,
  audio,
  failed = false,
  onRetry,
  className,
}: ChatBubbleProps) {
  const t = useTranslations();
  const mine = author === "user";

  return (
    <div className={cn("flex w-full", mine ? "justify-end" : "justify-start", className)}>
      <div
        className={cn(
          "flex max-w-reading flex-col gap-1 rounded-card px-3 py-2",
          mine
            ? "bg-gold-soft text-on-gold rounded-ee-none"
            : "bg-surface text-ink-primary border border-border-subtle rounded-es-none",
        )}
      >
        {audio ? (
          /* a voice note carries its own muted secondary text, which cannot sit
             on the tinted user bubble (ink-muted is 1.70:1 on gold-soft at
             night) — so inside a user bubble it gets a neutral surface */
          <div className={mine ? "rounded-card bg-surface p-2 text-ink-primary" : undefined}>
            {audio}
          </div>
        ) : (
          <p className="text-body">
            {content.map((part, i) =>
              isCited(part) ? (
                <button
                  key={`${part.spanId}-${i}`}
                  type="button"
                  onClick={() => onOpenTrust?.(part.spanId)}
                  aria-label={t("ui.chat.open_trust", { text: part.text })}
                  className={cn(
                    "underline decoration-gold underline-offset-4",
                    motionStandard,
                    focusRing,
                  )}
                >
                  {part.text}
                </button>
              ) : (
                <Fragment key={i}>{part}</Fragment>
              ),
            )}
          </p>
        )}

        <div className="flex items-center justify-end gap-2">
          {timestamp ? (
            <time className={cn("text-caption", mine ? "text-on-gold" : "text-ink-muted")}>
              {timestamp}
            </time>
          ) : null}
          {failed ? (
            <button
              type="button"
              onClick={onRetry}
              className={cn(
                "rounded-chip px-2 text-caption text-feedback-danger-text underline underline-offset-4",
                focusRing,
              )}
            >
              {t("ui.chat.retry")}
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
