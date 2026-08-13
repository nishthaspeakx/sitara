"use client";

/**
 * The thread: date pills, bubbles, timestamps, and the typing indicator.
 *
 * §25.4's grammar kept: bubbles left/right with tails, a date pill per day, the
 * timestamp inside the bubble, one ✓ for delivered-to-Tara.
 *
 * §25.4's grammar dropped, and unrepresentable rather than merely unwritten:
 * no read receipts (the delivery type has three states and none of them is
 * "read"), no forwarded labels, no group mechanics (a message has an author of
 * `user` or `tara`, and `ChatRole` has no third member).
 *
 * The long-press actions live here because they belong to a message, not to
 * the screen: copy · save to journal · remember this · why this? (guidance
 * bubbles only) · report.
 */

import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import type { ChatCitation } from "@sitara/schemas";

import { cn, focusRing } from "@/components/ui/_util";
import type { Message } from "@/lib/chat-thread";
import { groupByDay } from "@/lib/chat-thread";

import { MessageActions } from "./MessageActions";
import { MessageBubble } from "./MessageBubble";
import { TypingIndicator } from "./TypingIndicator";

function timeIn(locale: string, at: number): string {
  return new Intl.DateTimeFormat(locale, { hour: "numeric", minute: "2-digit" }).format(at);
}

/**
 * §25.4's date pill. "Today"/"Yesterday" are keys; anything older is formatted
 * in the user's locale — never an English month name inside a Hindi thread.
 */
function dayLabel(locale: string, at: number, t: (k: string) => string): string {
  const day = new Date(at);
  const today = new Date();
  const midnight = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const delta = (midnight(today) - midnight(day)) / 86_400_000;
  if (delta === 0) return t("ui.ask.date_today");
  if (delta === 1) return t("ui.ask.date_yesterday");
  return new Intl.DateTimeFormat(locale, { day: "numeric", month: "long" }).format(day);
}

export function MessageList({
  messages,
  locale,
  presenceLabelKey,
  onOpenTrust,
  onRetry,
  onQuote,
  onAction,
}: {
  messages: Message[];
  locale: string;
  /** Null while Tara is not working. */
  presenceLabelKey: "ui.ask.typing" | "ui.ask.listening" | null;
  onOpenTrust: (citation: ChatCitation) => void;
  onRetry: (id: string) => void;
  onQuote: (id: string) => void;
  onAction: (action: string, message: Message) => void;
}) {
  const t = useTranslations();
  const [openActions, setOpenActions] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [messages.length, presenceLabelKey]);

  return (
    <div
      data-testid="thread"
      role="log"
      aria-live="polite"
      className="flex flex-1 flex-col gap-3 overflow-y-auto px-4 py-4"
    >
      {groupByDay(messages).map((group) => (
        <div key={group.day} className="flex flex-col gap-3">
          <div className="flex justify-center">
            <span className="rounded-chip bg-surface-sunken px-3 py-1 text-caption text-ink-muted">
              {dayLabel(locale, group.items[0]!.at, t)}
            </span>
          </div>
          {group.items.map((message) => (
            <div
              key={message.id}
              data-testid={`message-${message.kind}`}
              // Long-press on touch, right-click on a pointer. Both open the
              // same sheet — §24.5's desktop rail has no long press.
              onContextMenu={(e) => {
                e.preventDefault();
                setOpenActions(message.id);
              }}
              className={cn("group flex flex-col", focusRing)}
            >
              <MessageBubble
                message={message}
                timestamp={timeIn(locale, message.at)}
                onOpenTrust={onOpenTrust}
                onRetry={() => onRetry(message.id)}
              />
              <button
                type="button"
                onClick={() => setOpenActions(message.id)}
                aria-label={t("ui.ask.actions_for")}
                className="sr-only focus:not-sr-only"
              />
            </div>
          ))}
        </div>
      ))}

      {presenceLabelKey ? <TypingIndicator labelKey={presenceLabelKey} /> : null}

      <MessageActions
        message={messages.find((m) => m.id === openActions) ?? null}
        onClose={() => setOpenActions(null)}
        onQuote={onQuote}
        onAction={onAction}
      />

      <div ref={bottom} />
    </div>
  );
}
