"use client";

/**
 * IconButton — §24.3 foundation.
 * An icon-only control always carries an accessible name from the catalogs;
 * `labelKey` is required, not optional, so a nameless button cannot ship.
 */

import { useTranslations } from "next-intl";
import type { ButtonHTMLAttributes, ReactNode } from "react";

import { cn, focusRing, motionStandard, touchTarget, type MessageKey } from "./_util";

export type IconButtonVariant = "plain" | "filled" | "outline";

const VARIANT: Record<IconButtonVariant, string> = {
  plain: "bg-transparent text-ink-primary hover:bg-surface-sunken",
  filled:
    "bg-interactive-primary text-on-gold border border-border-strong hover:bg-interactive-hover active:bg-interactive-pressed",
  outline: "bg-transparent text-ink-primary border border-border-strong hover:bg-surface-sunken",
};

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** i18n key for the accessible name — never a literal string (§2.4). */
  labelKey: MessageKey;
  icon: ReactNode;
  variant?: IconButtonVariant;
  /** Renders the pressed state of a toggle button (mute, speaker, captions…). */
  pressed?: boolean;
}

export function IconButton({
  labelKey,
  icon,
  variant = "plain",
  pressed,
  className,
  ...rest
}: IconButtonProps) {
  const t = useTranslations();
  return (
    <button
      {...rest}
      aria-label={t(labelKey)}
      aria-pressed={pressed}
      className={cn(
        "inline-flex items-center justify-center rounded-portrait",
        touchTarget,
        motionStandard,
        focusRing,
        VARIANT[variant],
        pressed && "bg-surface-sunken",
        "disabled:cursor-not-allowed disabled:text-ink-muted",
        className,
      )}
    >
      <span aria-hidden="true">{icon}</span>
    </button>
  );
}
