"use client";

/**
 * SegmentedControl — §24.3 foundation. Two to four mutually exclusive options
 * that all fit on screen (theme light/night, journal filters, tone presets).
 *
 * Keyboard model is a real tablist: arrows move, Home/End jump.
 */

import { useTranslations } from "next-intl";
import { useRef } from "react";

import { cn, controlHeight, focusRing, motionStandard, type MessageKey } from "./_util";

export interface Segment {
  value: string;
  labelKey: MessageKey;
}

export interface SegmentedControlProps {
  labelKey: MessageKey;
  segments: Segment[];
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  className?: string;
}

export function SegmentedControl({
  labelKey,
  segments,
  value,
  onChange,
  disabled,
  className,
}: SegmentedControlProps) {
  const t = useTranslations();
  const refs = useRef<Array<HTMLButtonElement | null>>([]);

  function onKeyDown(event: React.KeyboardEvent, index: number) {
    const last = segments.length - 1;
    let next: number | null = null;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") next = index === last ? 0 : index + 1;
    else if (event.key === "ArrowLeft" || event.key === "ArrowUp") next = index === 0 ? last : index - 1;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = last;
    if (next === null) return;
    const target = segments[next];
    if (!target) return;
    event.preventDefault();
    onChange(target.value);
    refs.current[next]?.focus();
  }

  return (
    <div
      role="tablist"
      aria-label={t(labelKey)}
      className={cn(
        "inline-flex rounded-chip border border-border-subtle bg-surface-sunken p-1",
        className,
      )}
    >
      {segments.map((segment, index) => {
        const active = segment.value === value;
        return (
          <button
            key={segment.value}
            ref={(el) => {
              refs.current[index] = el;
            }}
            type="button"
            role="tab"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            disabled={disabled}
            onClick={() => onChange(segment.value)}
            onKeyDown={(e) => onKeyDown(e, index)}
            className={cn(
              "rounded-chip px-4 text-caption",
              controlHeight,
              motionStandard,
              focusRing,
              active
                ? "bg-surface text-ink-primary shadow-card"
                : "bg-transparent text-ink-muted hover:text-ink-primary",
              disabled && "cursor-not-allowed opacity-60",
            )}
          >
            {t(segment.labelKey)}
          </button>
        );
      })}
    </div>
  );
}
