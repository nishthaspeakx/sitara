"use client";

/**
 * Divider — §24.3 structure. Purely decorative by default (aria-hidden), so it
 * never adds noise to the screen-reader tree. The `label` form is a real
 * separator with an accessible name ("or", a date break in the journal).
 */

import { useTranslations } from "next-intl";

import { cn, type MessageKey } from "./_util";

export interface DividerProps {
  /** Renders the rule with centred label text. */
  labelKey?: MessageKey;
  orientation?: "horizontal" | "vertical";
  className?: string;
}

export function Divider({ labelKey, orientation = "horizontal", className }: DividerProps) {
  const t = useTranslations();

  if (orientation === "vertical") {
    return (
      <span
        aria-hidden="true"
        className={cn("inline-block w-px self-stretch bg-border-subtle", className)}
      />
    );
  }

  if (!labelKey) {
    return <hr aria-hidden="true" className={cn("h-px border-0 bg-border-subtle", className)} />;
  }

  return (
    <div role="separator" aria-label={t(labelKey)} className={cn("flex items-center gap-3", className)}>
      <span aria-hidden="true" className="h-px flex-1 bg-border-subtle" />
      <span className="text-caption text-ink-muted">{t(labelKey)}</span>
      <span aria-hidden="true" className="h-px flex-1 bg-border-subtle" />
    </div>
  );
}
