"use client";

/**
 * Header — §24.3 structure, three variants:
 *
 *  · `presence` — Today and Ask Tara. Carries Tara's portrait chip, which §24.1
 *    makes persistent on exactly these two surfaces (collapsed 56px, expands on
 *    voice/ceremony).
 *  · `titled`   — an ordinary screen title with an optional back control.
 *  · `bare`     — onboarding and ceremony screens, which have no header chrome
 *    (§24.4: language selection has no header).
 *
 * Back is browser-native and never traps (§24.1).
 */

import { ChevronLeft } from "lucide-react";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { TaraPresence } from "./TaraPresence";
import {
  ICON_STROKE,
  cn,
  focusRing,
  touchTarget,
  type MessageKey,
  type TaraState,
} from "./_util";

export type HeaderVariant = "presence" | "titled" | "bare";

export interface HeaderProps {
  variant?: HeaderVariant;
  titleKey?: MessageKey;
  /** User data (a family member's name, a date) rather than a key. */
  title?: string;
  subtitleKey?: MessageKey;
  onBack?: () => void;
  /** Trailing controls — settings, search, overflow. */
  actions?: ReactNode;
  /** presence variant only. */
  taraState?: TaraState;
  /** presence variant only — expands the chip during voice/ceremony. */
  taraExpanded?: boolean;
  className?: string;
}

export function Header({
  variant = "titled",
  titleKey,
  title,
  subtitleKey,
  onBack,
  actions,
  taraState = "warm_neutral",
  taraExpanded = false,
  className,
}: HeaderProps) {
  const t = useTranslations();

  if (variant === "bare") {
    return (
      <header className={cn("flex items-center justify-between gap-2 px-4 py-2", className)}>
        {onBack ? <BackButton onBack={onBack} /> : <span />}
        {actions}
      </header>
    );
  }

  return (
    <header
      className={cn(
        // standalone-PWA safe area (§24.5)
        "flex items-center gap-3 border-b border-border-subtle bg-surface px-4 py-2 pt-[env(safe-area-inset-top)]",
        className,
      )}
    >
      {onBack ? <BackButton onBack={onBack} /> : null}

      {variant === "presence" ? (
        <TaraPresence
          size={taraExpanded ? "md" : "sm"}
          state={taraState}
          showAiLabel
          className="shrink-0"
        />
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col">
        <h1 className="truncate font-serif text-h3 text-ink-primary">
          {titleKey ? t(titleKey) : title}
        </h1>
        {subtitleKey ? (
          <p className="truncate text-caption text-ink-muted">{t(subtitleKey)}</p>
        ) : null}
      </div>

      {actions ? <div className="flex shrink-0 items-center gap-1">{actions}</div> : null}
    </header>
  );
}

function BackButton({ onBack }: { onBack: () => void }) {
  const t = useTranslations();
  return (
    <button
      type="button"
      onClick={onBack}
      aria-label={t("ui.back")}
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-portrait text-ink-primary",
        touchTarget,
        focusRing,
      )}
    >
      <ChevronLeft aria-hidden="true" strokeWidth={ICON_STROKE} className="rtl:rotate-180" />
    </button>
  );
}
