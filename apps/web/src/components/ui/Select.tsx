"use client";

/**
 * Select / Sheet-picker — §24.3 foundation.
 *
 * Mobile-first: the options open in a Sheet rather than a native dropdown, so
 * long Indic option labels get full width instead of a clipped menu. Options
 * are supplied as message KEYS.
 */

import { Check, ChevronDown } from "lucide-react";
import { useTranslations } from "next-intl";
import { useId, useState } from "react";

import { Sheet } from "./Sheet";
import {
  ICON_STROKE,
  cn,
  controlHeight,
  focusRing,
  motionStandard,
  touchTarget,
  type MessageKey,
} from "./_util";

export interface SelectOption {
  value: string;
  labelKey: MessageKey;
  /** Optional second line — e.g. the script name under a language name. */
  detailKey?: MessageKey;
}

export interface SelectProps {
  labelKey: MessageKey;
  /** Sheet heading; defaults to the field label. */
  titleKey?: MessageKey;
  options: SelectOption[];
  value: string | null;
  onChange: (value: string) => void;
  placeholderKey?: MessageKey;
  disabled?: boolean;
  className?: string;
  /** Test/story hook: render the sheet open. */
  defaultOpen?: boolean;
}

export function Select({
  labelKey,
  titleKey,
  options,
  value,
  onChange,
  placeholderKey = "ui.select.choose",
  disabled,
  className,
  defaultOpen = false,
}: SelectProps) {
  const t = useTranslations();
  const id = useId();
  const [open, setOpen] = useState(defaultOpen);
  const selected = options.find((o) => o.value === value) ?? null;

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <span id={`${id}-label`} className="text-caption text-ink-muted">
        {t(labelKey)}
      </span>
      <button
        type="button"
        aria-labelledby={`${id}-label`}
        aria-haspopup="dialog"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => setOpen(true)}
        className={cn(
          "flex w-full items-center justify-between gap-2 rounded-chip border border-border-strong bg-surface px-3 text-start text-body",
          controlHeight,
          motionStandard,
          focusRing,
          selected ? "text-ink-primary" : "text-ink-muted",
          "disabled:bg-surface-sunken disabled:cursor-not-allowed",
        )}
      >
        <span>{selected ? t(selected.labelKey) : t(placeholderKey)}</span>
        <ChevronDown aria-hidden="true" strokeWidth={ICON_STROKE} className="shrink-0" />
      </button>

      <Sheet open={open} onClose={() => setOpen(false)} titleKey={titleKey ?? labelKey}>
        <ul role="listbox" aria-labelledby={`${id}-label`} className="flex flex-col">
          {options.map((option) => {
            const isSelected = option.value === value;
            return (
              <li key={option.value}>
                <button
                  type="button"
                  role="option"
                  aria-selected={isSelected}
                  onClick={() => {
                    onChange(option.value);
                    setOpen(false);
                  }}
                  className={cn(
                    "flex w-full items-center justify-between gap-3 rounded-chip px-3 py-3 text-start",
                    touchTarget,
                    motionStandard,
                    focusRing,
                    isSelected ? "bg-surface-sunken" : "hover:bg-surface-sunken",
                  )}
                >
                  <span className="flex flex-col">
                    <span className="text-body text-ink-primary">{t(option.labelKey)}</span>
                    {option.detailKey ? (
                      <span className="text-caption text-ink-muted">{t(option.detailKey)}</span>
                    ) : null}
                  </span>
                  {isSelected ? (
                    <Check aria-hidden="true" strokeWidth={ICON_STROKE} className="shrink-0" />
                  ) : null}
                </button>
              </li>
            );
          })}
        </ul>
      </Sheet>
    </div>
  );
}
