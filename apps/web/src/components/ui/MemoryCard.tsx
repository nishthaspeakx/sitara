"use client";

/**
 * MemoryCard — §24.3 / §32.4. The vault row: type icon + consent stamp.
 *
 * The 11 memory types are §32.4's closed set. The consent stamp is not
 * decoration — §30.4 requires the source turn to stay linked and correction to
 * stay one tap away, so every card carries when it was agreed and how to change it.
 */

import {
  CalendarHeart,
  Compass,
  Heart,
  HeartPulse,
  Home,
  Languages,
  MessageSquareQuote,
  Sparkles,
  Star,
  Target,
  Users,
} from "lucide-react";
import { useTranslations } from "next-intl";
import type { ComponentType } from "react";

import { Card } from "./Card";
import { ICON_STROKE, cn, focusRing, motionStandard } from "./_util";

/** §32.4 — the 11 memory types (closed set). */
export const MEMORY_TYPES = [
  "life_fact",
  "relationship",
  "preference",
  "goal",
  "concern",
  "health_context",
  "belief_practice",
  "important_date",
  "name_pronunciation",
  "language_style",
  "conversation_thread",
] as const;
export type MemoryType = (typeof MEMORY_TYPES)[number];

const TYPE_ICON: Record<MemoryType, ComponentType<{ strokeWidth?: number; className?: string }>> = {
  life_fact: Star,
  relationship: Users,
  preference: Heart,
  goal: Target,
  concern: Compass,
  health_context: HeartPulse,
  belief_practice: Sparkles,
  important_date: CalendarHeart,
  name_pronunciation: Languages,
  language_style: Languages,
  conversation_thread: MessageSquareQuote,
};

export interface MemoryCardProps {
  type: MemoryType;
  /** The remembered content, already localised. */
  content: string;
  /** Formatted by the caller in the user's locale — never a raw ISO string. */
  consentedOn: string;
  onOpen?: () => void;
  /** Jumps to the turn this came from (§30.4). */
  onOpenSource?: () => void;
  className?: string;
}

export function MemoryCard({
  type,
  content,
  consentedOn,
  onOpen,
  onOpenSource,
  className,
}: MemoryCardProps) {
  const t = useTranslations();
  const Icon = TYPE_ICON[type] ?? Home;

  return (
    <Card onClick={onOpen} className={cn("flex flex-col gap-2", className)}>
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className="mt-1 shrink-0 rounded-portrait bg-surface-sunken p-2 text-ink-muted"
        >
          <Icon strokeWidth={ICON_STROKE} className="h-4 w-4" />
        </span>
        <div className="flex min-w-0 flex-col gap-1">
          <span className="text-caption text-ink-muted">{t(`ui.memory.type.${type}`)}</span>
          <p className="text-body text-ink-primary">{content}</p>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 border-t border-border-subtle pt-2">
        <span className="text-caption text-ink-muted">
          {t("ui.memory.consent_stamp", { date: consentedOn })}
        </span>
        {onOpenSource ? (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onOpenSource();
            }}
            className={cn(
              "rounded-chip px-2 py-1 text-caption text-ink-primary underline decoration-gold underline-offset-4",
              motionStandard,
              focusRing,
            )}
          >
            {t("ui.memory.source_turn")}
          </button>
        ) : null}
      </div>
    </Card>
  );
}
