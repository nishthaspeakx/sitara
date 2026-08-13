"use client";

/**
 * §25.4's long-press actions, and exactly those five:
 *
 *   copy · save to journal · remember this → memory chip ·
 *   why this? (guidance bubbles only) · report
 *
 * "Guidance bubbles only" is enforced by the data rather than by a condition
 * someone maintains: "why this?" appears when the turn carries citations, and
 * a turn carries citations only when the grounding validator found a claim
 * standing on a served fact. A bubble with nothing to explain offers no
 * explanation.
 *
 * Swipe-to-reply lives on the same sheet as "reply", because a swipe is not
 * discoverable and §25.4's demographic is the reason this screen exists.
 */

import { BookmarkPlus, Copy, CornerUpLeft, Flag, HelpCircle, NotebookPen } from "lucide-react";
import { useTranslations } from "next-intl";

import { Sheet } from "@/components/ui";
import { ICON_STROKE, cn, focusRing, touchTarget } from "@/components/ui/_util";
import type { Message } from "@/lib/chat-thread";

const ROW = cn(
  "flex w-full items-center gap-3 rounded-card px-3 text-start text-body text-ink-primary hover:bg-surface-sunken",
  touchTarget,
  focusRing,
);

export function MessageActions({
  message,
  onClose,
  onQuote,
  onAction,
}: {
  message: Message | null;
  onClose: () => void;
  onQuote: (id: string) => void;
  onAction: (action: string, message: Message) => void;
}) {
  const t = useTranslations();
  const isGuidance = message?.kind === "tara" && message.turn.citations.length > 0;

  return (
    <Sheet open={message !== null} onClose={onClose} titleKey="ui.ask.actions_for">
      {message ? (
        <div className="flex flex-col gap-1">
          <button
            type="button"
            className={ROW}
            onClick={() => {
              onQuote(message.id);
              onClose();
            }}
          >
            <CornerUpLeft aria-hidden="true" strokeWidth={ICON_STROKE} className="h-5 w-5" />
            {t("ui.ask.quoting")}
          </button>

          <button
            type="button"
            className={ROW}
            onClick={() => {
              onAction("copy", message);
              onClose();
            }}
          >
            <Copy aria-hidden="true" strokeWidth={ICON_STROKE} className="h-5 w-5" />
            {t("ui.ask.action_copy")}
          </button>

          <button
            type="button"
            className={ROW}
            onClick={() => {
              onAction("journal", message);
              onClose();
            }}
          >
            <NotebookPen aria-hidden="true" strokeWidth={ICON_STROKE} className="h-5 w-5" />
            {t("ui.ask.action_journal")}
          </button>

          <button
            type="button"
            className={ROW}
            onClick={() => {
              onAction("remember", message);
              onClose();
            }}
          >
            <BookmarkPlus aria-hidden="true" strokeWidth={ICON_STROKE} className="h-5 w-5" />
            {t("ui.ask.action_remember")}
          </button>

          {isGuidance ? (
            <button
              type="button"
              className={ROW}
              onClick={() => {
                onAction("why", message);
                onClose();
              }}
            >
              <HelpCircle aria-hidden="true" strokeWidth={ICON_STROKE} className="h-5 w-5" />
              {t("ui.ask.action_why")}
            </button>
          ) : null}

          <button
            type="button"
            className={ROW}
            onClick={() => {
              onAction("report", message);
              onClose();
            }}
          >
            <Flag aria-hidden="true" strokeWidth={ICON_STROKE} className="h-5 w-5" />
            {t("ui.ask.action_report")}
          </button>
        </div>
      ) : null}
    </Sheet>
  );
}
