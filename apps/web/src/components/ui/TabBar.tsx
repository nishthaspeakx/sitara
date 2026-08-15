"use client";

/**
 * TabBar — §24.3 structure, §24.1 navigation decision (FINAL).
 *
 * FOUR tabs: Today · Ask Tara · Journal · You. Night reflection is Today's
 * evening state, NOT a fifth tab. At ≥1100px the rail replaces this (§29.3);
 * at ≤320px the labels hide and the icons carry the tabs.
 */

import { CalendarDays, MessageCircleHeart, NotebookPen, UserRound } from "lucide-react";
import { useTranslations } from "next-intl";
import type { ComponentType } from "react";

import { ICON_STROKE, cn, focusRing, motionStandard, touchTarget } from "./_util";

export const TABS = ["today", "ask", "journal", "you"] as const;
export type TabId = (typeof TABS)[number];

const ICONS: Record<TabId, ComponentType<{ strokeWidth?: number; className?: string }>> = {
  today: CalendarDays,
  ask: MessageCircleHeart,
  journal: NotebookPen,
  you: UserRound,
};

export interface TabBarProps {
  active: TabId;
  onSelect: (tab: TabId) => void;
  /** Unread/attention counts per tab. */
  badges?: Partial<Record<TabId, number>>;
  className?: string;
}

export function TabBar({ active, onSelect, badges, className }: TabBarProps) {
  const t = useTranslations();
  return (
    <nav
      aria-label={t("ui.tabs.label")}
      className={cn(
        // safe-area inset for the iOS home bar (§24.5)
        "flex w-full items-stretch border-t border-border-subtle bg-surface pb-safe",
        className,
      )}
    >
      {TABS.map((tab) => {
        const Icon = ICONS[tab];
        const isActive = tab === active;
        const badge = badges?.[tab];
        return (
          <button
            key={tab}
            type="button"
            aria-current={isActive ? "page" : undefined}
            onClick={() => onSelect(tab)}
            className={cn(
              "relative flex flex-1 flex-col items-center justify-center gap-1 py-2",
              touchTarget,
              motionStandard,
              focusRing,
              isActive ? "text-ink-primary" : "text-ink-muted",
            )}
          >
            <span className="relative">
              <Icon aria-hidden="true" strokeWidth={ICON_STROKE} />
              {badge ? (
                <span className="absolute -end-2 -top-1 rounded-portrait bg-interactive-primary px-1 text-caption text-on-gold">
                  {badge}
                </span>
              ) : null}
            </span>
            {/* §29.3: at 320px the labels hide and the icons carry the tabs */}
            <span className="hidden text-caption phone:inline">{t(`ui.tabs.${tab}`)}</span>
            {isActive ? (
              <span
                aria-hidden="true"
                className="absolute inset-x-4 bottom-0 h-1 rounded-chip bg-interactive-primary"
              />
            ) : null}
          </button>
        );
      })}
    </nav>
  );
}
