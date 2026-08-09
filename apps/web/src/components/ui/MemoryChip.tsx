"use client";

/**
 * MemoryChip — §24.3 / §32.4. Micro-states: offer · accepted · declined.
 *
 * §32.4/§32.5: a memory is OFFERED, never taken. The offer state carries two
 * equal-weight controls — remembering is not the default and declining is not a
 * smaller button (§29.2, no dark patterns). Once answered the chip becomes a
 * quiet stamp, and "don't remember this" stays reachable (§30.4).
 */

import { Check, X, BookmarkPlus } from "lucide-react";
import { useTranslations } from "next-intl";

import { ICON_STROKE, cn, focusRing, motionStandard, touchTarget } from "./_util";

export type MemoryChipState = "offer" | "accepted" | "declined";

export interface MemoryChipProps {
  state: MemoryChipState;
  /** What Tara is offering to remember, already localised. */
  summary: string;
  onAccept?: () => void;
  onDecline?: () => void;
  /** §30.4 — "don't remember this", available after accepting. */
  onForget?: () => void;
  className?: string;
}

export function MemoryChip({
  state,
  summary,
  onAccept,
  onDecline,
  onForget,
  className,
}: MemoryChipProps) {
  const t = useTranslations();

  if (state === "offer") {
    return (
      <div
        className={cn(
          "flex flex-col gap-2 rounded-chip border border-dashed border-border-strong bg-surface p-3",
          className,
        )}
      >
        <p className="text-caption text-ink-muted">{t("ui.memory.offer")}</p>
        <p className="text-body text-ink-primary">{summary}</p>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onAccept}
            className={cn(
              "inline-flex items-center gap-2 rounded-chip border border-border-strong bg-gold-soft px-3 py-2 text-caption text-on-gold",
              touchTarget,
              motionStandard,
              focusRing,
            )}
          >
            <BookmarkPlus aria-hidden="true" strokeWidth={ICON_STROKE} className="h-4 w-4" />
            {t("ui.memory.accept")}
          </button>
          <button
            type="button"
            onClick={onDecline}
            className={cn(
              "inline-flex items-center gap-2 rounded-chip border border-border-strong bg-surface px-3 py-2 text-caption text-ink-primary",
              touchTarget,
              motionStandard,
              focusRing,
            )}
          >
            <X aria-hidden="true" strokeWidth={ICON_STROKE} className="h-4 w-4" />
            {t("ui.memory.decline")}
          </button>
        </div>
      </div>
    );
  }

  const accepted = state === "accepted";
  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-chip border border-border-subtle bg-surface-sunken px-3 py-2",
        className,
      )}
    >
      <span aria-hidden="true" className="text-ink-muted">
        {accepted ? (
          <Check strokeWidth={ICON_STROKE} className="h-4 w-4" />
        ) : (
          <X strokeWidth={ICON_STROKE} className="h-4 w-4" />
        )}
      </span>
      <span className="min-w-0 flex-1 truncate text-caption text-ink-muted">
        {t(accepted ? "ui.memory.accepted" : "ui.memory.declined")}
      </span>
      {accepted && onForget ? (
        <button
          type="button"
          onClick={onForget}
          className={cn(
            "shrink-0 rounded-chip px-2 py-1 text-caption text-ink-primary underline decoration-gold underline-offset-4",
            focusRing,
          )}
        >
          {t("ui.memory.forget")}
        </button>
      ) : null}
    </div>
  );
}
