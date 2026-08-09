"use client";

/** SearchField — §24.3 foundation. Journal/chat search (S23, Atlas Search). */

import { Search, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useId } from "react";

import { ICON_STROKE, cn, controlHeight, focusRing, motionStandard, touchTarget } from "./_util";

export interface SearchFieldProps {
  value: string;
  onChange: (value: string) => void;
  onClear?: () => void;
  placeholderKey?: string;
  labelKey?: string;
  disabled?: boolean;
  className?: string;
}

export function SearchField({
  value,
  onChange,
  onClear,
  placeholderKey = "ui.search.placeholder",
  labelKey = "ui.search.label",
  disabled,
  className,
}: SearchFieldProps) {
  const t = useTranslations();
  const id = useId();
  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <label htmlFor={id} className="text-caption text-ink-muted">
        {t(labelKey)}
      </label>
      <div
        className={cn(
          "flex items-center gap-2 rounded-chip border border-border-strong bg-surface px-3",
          controlHeight,
          motionStandard,
          "focus-within:outline focus-within:outline-focus focus-within:outline-offset-focus " +
            "focus-within:outline-focus-ring focus-within:shadow-focus",
        )}
      >
        <Search aria-hidden="true" strokeWidth={ICON_STROKE} className="shrink-0 text-ink-muted" />
        <input
          id={id}
          type="search"
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          placeholder={t(placeholderKey)}
          className="w-full bg-transparent text-body text-ink-primary outline-none placeholder:text-ink-muted"
        />
        {value ? (
          <button
            type="button"
            onClick={() => (onClear ? onClear() : onChange(""))}
            aria-label={t("ui.search.clear")}
            className={cn(
              "inline-flex items-center justify-center rounded-portrait text-ink-muted",
              touchTarget,
              focusRing,
            )}
          >
            <X aria-hidden="true" strokeWidth={ICON_STROKE} />
          </button>
        ) : null}
      </div>
    </div>
  );
}
