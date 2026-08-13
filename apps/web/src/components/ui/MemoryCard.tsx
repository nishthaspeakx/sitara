"use client";

/**
 * MemoryCard — §24.3 / §32.4. The vault row: type icon + consent stamp.
 *
 * The 11 memory types are §32.4's closed set. The consent stamp is not
 * decoration — §30.4 requires the source turn to stay linked and correction to
 * stay one tap away, so every card carries when it was agreed and how to change it.
 */

import {
  Briefcase,
  CalendarHeart,
  CloudSun,
  Compass,
  Heart,
  Home,
  Languages,
  Leaf,
  Sparkles,
  Star,
  Target,
  Users,
} from "lucide-react";
import { useTranslations } from "next-intl";
import type { ComponentType } from "react";

import { MEMORY_TYPES, type MemoryType } from "@sitara/schemas";

import { Card } from "./Card";
import { ICON_STROKE, cn, focusRing, motionStandard } from "./_util";

/**
 * §32.4 — the 11 memory types (closed set), from `@sitara/schemas`.
 *
 * This file used to declare its own eleven, and it was a DIFFERENT eleven:
 * `life_fact`, `concern`, `belief_practice`, `conversation_thread` and three
 * more that §32.4 does not contain, while `significant_event`,
 * `decision_context`, `mood_pattern`, `spiritual_practice` and the rest were
 * missing. §32.4 ends "Vault filters use exactly these 11 labels, localized",
 * so a vault built on this list would have filtered by a taxonomy the memory
 * module has never written a row under.
 */
export { MEMORY_TYPES, type MemoryType };

const TYPE_ICON: Record<MemoryType, ComponentType<{ strokeWidth?: number; className?: string }>> = {
  person: Users,
  significant_event: Star,
  date_anniversary: CalendarHeart,
  preference: Heart,
  goal_intention: Target,
  decision_context: Compass,
  mood_pattern: CloudSun,
  // §32.4 type 8 is non-medical framing ONLY — symptoms and diagnoses are
  // declined at classification, in code as well as in the model. So the glyph
  // is not a clinical one: a pulse trace next to a memory the user was
  // promised is "health-ADJACENT" reads as a medical record, which is the one
  // thing this type is defined not to be.
  health_adjacent: Leaf,
  work_finance: Briefcase,
  spiritual_practice: Sparkles,
  pronunciation_identity: Languages,
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
