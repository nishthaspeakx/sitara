"use client";

/**
 * §25.4's header: photo + name + AI-guide label + status ring + presence line.
 *
 * Two rules the shape enforces rather than the reviewer:
 *
 * **No "online" / "last seen" theatre.** §25.4 names it directly. The presence
 * line is a constant — "here for you" — because it is a promise about what the
 * app is, not a claim about a socket. There is no prop here that could carry a
 * timestamp or a connection state, so a later screen cannot start reporting
 * one without adding the field and being noticed.
 *
 * **The ring is `StoryRing` with `enabled` left at its default false** (§30.6,
 * P1-gated). The component's own default hides it, so a P0 build renders no
 * ring even if this file forgot to say so — which is why it is not passed.
 *
 * The portrait state IS the served one at L2+: §29.5 puts state 11 in the chat
 * header and nowhere else.
 *
 * **The call button is §29's entry point** ("call button in Ask header") and is
 * behind `CALLS_ENABLED`, which is off — §33.5 gates live calls on six measures
 * and four of them are not passing. `features.ts` carries the reasoning. With
 * the flag off the control does not render at all rather than rendering
 * disabled: a greyed call button asserts that calling is a thing this account
 * could do, and §30.1's parity rule wants the working alternative visible
 * instead — which is the mic the composer already has.
 */

import { Phone } from "lucide-react";
import { useTranslations } from "next-intl";
import type { PresenceState } from "@sitara/schemas";

import { IconButton, StoryRing } from "@/components/ui";
import { ICON_STROKE } from "@/components/ui/_util";
import { CALLS_ENABLED } from "@/lib/features";

export interface ChatHeaderProps {
  presenceState: PresenceState;
  /** Opens §25.3's screen 17. Absent when the caller has no call route. */
  onCall?: () => void;
}

export function ChatHeader({ presenceState, onCall }: ChatHeaderProps) {
  const t = useTranslations();

  return (
    <header
      data-testid="ask-header"
      className="flex items-center gap-3 border-b border-border-subtle bg-surface px-4 py-2 pt-[env(safe-area-inset-top)]"
    >
      <StoryRing size="sm" taraState={presenceState} />
      <div className="flex min-w-0 flex-col">
        <span className="truncate text-body text-ink-primary">{t("ui.tara.name")}</span>
        {/* CC-008: the disclosure is permanent wherever her name or face appears. */}
        <span className="truncate text-caption text-ink-muted">{t("ui.tara.ai_label")}</span>
      </div>
      <span className="ms-auto shrink-0 text-caption text-ink-muted">
        {t("ui.ask.presence_line")}
      </span>
      {CALLS_ENABLED && onCall ? (
        <IconButton
          variant="plain"
          labelKey="ui.call.start"
          onClick={onCall}
          icon={<Phone strokeWidth={ICON_STROKE} />}
        />
      ) : null}
    </header>
  );
}
