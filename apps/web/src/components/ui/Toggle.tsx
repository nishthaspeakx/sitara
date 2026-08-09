"use client";

/**
 * Toggle — §24.3 foundation. A switch, not a checkbox: it takes effect
 * immediately, so there is never a "save" the user can miss.
 *
 * State is carried by position AND by the on/off label, never by colour alone
 * (§29.4).
 */

import { useTranslations } from "next-intl";
import { useId } from "react";

import { cn, focusRing, motionStandard, touchTarget, type MessageKey } from "./_util";

export interface ToggleProps {
  labelKey: MessageKey;
  descriptionKey?: MessageKey;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  className?: string;
}

export function Toggle({
  labelKey,
  descriptionKey,
  checked,
  onChange,
  disabled,
  className,
}: ToggleProps) {
  const t = useTranslations();
  const id = useId();
  return (
    <div className={cn("flex items-center justify-between gap-4", className)}>
      <span className="flex flex-col">
        <label htmlFor={id} className="text-body text-ink-primary">
          {t(labelKey)}
        </label>
        {descriptionKey ? (
          <span className="text-caption text-ink-muted">{t(descriptionKey)}</span>
        ) : null}
      </span>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative inline-flex shrink-0 items-center rounded-portrait border px-1",
          "h-8 w-12",
          touchTarget,
          motionStandard,
          focusRing,
          checked
            ? "bg-interactive-primary border-border-strong"
            : "bg-interactive-disabled border-border-subtle",
          disabled && "cursor-not-allowed opacity-60",
        )}
      >
        <span
          aria-hidden="true"
          className={cn(
            "block h-6 w-6 rounded-portrait bg-surface",
            motionStandard,
            checked ? "translate-x-4 rtl:-translate-x-4" : "translate-x-0",
          )}
        />
        <span className="sr-only">{checked ? t("ui.toggle.on") : t("ui.toggle.off")}</span>
      </button>
    </div>
  );
}
