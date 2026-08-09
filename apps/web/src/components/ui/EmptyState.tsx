"use client";

/**
 * EmptyState — §24.3 feedback. Illustration + ONE line + ONE action.
 *
 * §24.6 fixes the count at NINE designed empty states and the rule that there
 * are no dead ends. `EMPTY_STATES` is that closed list, so a tenth cannot
 * appear without a design-system review (§24.3 PR template rule).
 *
 * The illustration system is deliberately distinct from Tara's photographic
 * presence (§24.7), and §29.5 forbids Tara from being the face of an empty or
 * failed screen — hence the constellation motif rather than a portrait.
 */

import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { Button } from "./Button";
import { cn } from "./_util";

/** §24.6 — the nine designed empty states. */
export const EMPTY_STATES = [
  "memories",
  "journal",
  "chat_history",
  "search_results",
  "family",
  "saved_guidance",
  "reflections",
  "receipts",
  "notifications",
] as const;
export type EmptyStateId = (typeof EMPTY_STATES)[number];

export interface EmptyStateProps {
  id: EmptyStateId;
  /** The one action. Omit only where genuinely nothing can be done here. */
  onAction?: () => void;
  /** Per-state illustration slot; falls back to the constellation motif. */
  illustration?: ReactNode;
  className?: string;
}

export function EmptyState({ id, onAction, illustration, className }: EmptyStateProps) {
  const t = useTranslations();
  return (
    <div
      className={cn(
        "flex max-w-reading flex-col items-center gap-3 px-4 py-8 text-center",
        className,
      )}
    >
      <span aria-hidden="true">{illustration ?? <EmptyMark />}</span>
      <p className="text-body text-ink-muted">{t(`ui.empty.${id}`)}</p>
      {onAction ? <Button onClick={onAction}>{t(`ui.empty.${id}_action`)}</Button> : null}
    </div>
  );
}

/** Illustration-system placeholder: the midnight/cream constellation motif. */
function EmptyMark() {
  return (
    <svg viewBox="0 0 96 64" className="h-16 w-24" role="presentation">
      <g className="stroke-border-strong" strokeWidth="1.5" fill="none">
        <path d="M14 44 L32 20 L52 34 L72 14 L86 26" strokeLinecap="round" strokeLinejoin="round" />
      </g>
      <g className="fill-gold-soft">
        <circle cx="14" cy="44" r="2.5" />
        <circle cx="32" cy="20" r="3" />
        <circle cx="52" cy="34" r="2.5" />
        <circle cx="72" cy="14" r="3" />
        <circle cx="86" cy="26" r="2.5" />
      </g>
    </svg>
  );
}
