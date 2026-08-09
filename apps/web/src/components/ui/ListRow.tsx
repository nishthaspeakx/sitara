"use client";

/** ListRow — §24.3 structure. Settings rows, family lists, journal entries. */

import { ChevronRight } from "lucide-react";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import {
  ICON_STROKE,
  cn,
  focusRing,
  motionStandard,
  touchTarget,
  type MessageKey,
} from "./_util";

export interface ListRowProps {
  labelKey?: MessageKey;
  /** Use when the label is user data (a name, a city) rather than a key. */
  label?: string;
  detailKey?: MessageKey;
  detail?: string;
  leading?: ReactNode;
  /** Right-hand content — a value, a Toggle, a badge. */
  trailing?: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  className?: string;
}

export function ListRow({
  labelKey,
  label,
  detailKey,
  detail,
  leading,
  trailing,
  onClick,
  disabled,
  className,
}: ListRowProps) {
  const t = useTranslations();
  const body = (
    <>
      {leading ? (
        <span aria-hidden="true" className="shrink-0 text-ink-muted">
          {leading}
        </span>
      ) : null}
      <span className="flex min-w-0 flex-1 flex-col text-start">
        <span className="truncate text-body text-ink-primary">
          {labelKey ? t(labelKey) : label}
        </span>
        {detailKey || detail ? (
          <span className="truncate text-caption text-ink-muted">
            {detailKey ? t(detailKey) : detail}
          </span>
        ) : null}
      </span>
      {trailing ? <span className="shrink-0">{trailing}</span> : null}
      {onClick ? (
        <ChevronRight
          aria-hidden="true"
          strokeWidth={ICON_STROKE}
          className="shrink-0 text-ink-muted rtl:rotate-180"
        />
      ) : null}
    </>
  );

  const classes = cn(
    "flex w-full items-center gap-3 border-b border-border-subtle bg-surface px-4 py-3",
    touchTarget,
    className,
  );

  if (!onClick) return <div className={classes}>{body}</div>;
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        classes,
        motionStandard,
        focusRing,
        "hover:bg-surface-sunken disabled:cursor-not-allowed disabled:text-ink-muted",
      )}
    >
      {body}
    </button>
  );
}
