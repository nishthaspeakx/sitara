"use client";

/**
 * Slider — §24.3 foundation, specced for the brief-time picker (onboarding
 * step 13, S35 settings). The value is announced as a formatted time so a
 * screen-reader user hears "07:00", not "28".
 */

import { useTranslations } from "next-intl";
import { useId } from "react";

import { cn, focusRing, type MessageKey } from "./_util";

export interface SliderProps {
  labelKey: MessageKey;
  min: number;
  max: number;
  step?: number;
  value: number;
  onChange: (value: number) => void;
  /** Turns the raw value into the text shown and announced (e.g. 07:00). */
  format: (value: number) => string;
  disabled?: boolean;
  className?: string;
}

export function Slider({
  labelKey,
  min,
  max,
  step = 1,
  value,
  onChange,
  format,
  disabled,
  className,
}: SliderProps) {
  const t = useTranslations();
  const id = useId();
  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <div className="flex items-baseline justify-between gap-4">
        <label htmlFor={id} className="text-caption text-ink-muted">
          {t(labelKey)}
        </label>
        <output htmlFor={id} className="text-h3 text-ink-primary font-serif">
          {format(value)}
        </output>
      </div>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        aria-valuetext={format(value)}
        onChange={(e) => onChange(Number(e.target.value))}
        className={cn(
          "w-full appearance-none rounded-chip bg-interactive-disabled",
          "h-2 accent-[color:var(--color-interactive-primary)]",
          focusRing,
          disabled && "cursor-not-allowed opacity-60",
        )}
      />
    </div>
  );
}
