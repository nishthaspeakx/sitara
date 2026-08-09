"use client";

/**
 * SectionHeader — §24.3 structure. Serif, per §24.2: the brand serif carries
 * Tara's ceremonial lines and the section headers; Inter carries the UI.
 */

import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { cn, type MessageKey } from "./_util";

export interface SectionHeaderProps {
  titleKey: MessageKey;
  subtitleKey?: MessageKey;
  /** A single trailing control — "see all", a filter, a count. */
  action?: ReactNode;
  level?: 2 | 3;
  className?: string;
}

export function SectionHeader({
  titleKey,
  subtitleKey,
  action,
  level = 2,
  className,
}: SectionHeaderProps) {
  const t = useTranslations();
  const Tag = level === 2 ? "h2" : "h3";
  return (
    <div className={cn("flex items-end justify-between gap-4 py-2", className)}>
      <div className="flex flex-col gap-1">
        <Tag className={cn("font-serif text-ink-primary", level === 2 ? "text-h2" : "text-h3")}>
          {t(titleKey)}
        </Tag>
        {subtitleKey ? <p className="text-caption text-ink-muted">{t(subtitleKey)}</p> : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}
