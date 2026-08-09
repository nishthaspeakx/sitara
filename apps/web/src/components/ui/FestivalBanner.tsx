"use client";

/**
 * FestivalBanner — §24.3 Sitara-specific, with per-tradition art slots.
 *
 * §4.2 / §24.7: the art is illustration, never sectarian religious imagery and
 * never stock photography. The tradition is named, not assumed — a Tamil user's
 * Pongal and a Gujarati user's Uttarayan are the same date and different
 * framings, so the banner always states whose observance it is showing.
 */

import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { cn, focusRing, motionStandard } from "./_util";

export interface FestivalBannerProps {
  /** Festival name, already localised and glossary-checked. */
  name: string;
  /** The regional framing, e.g. "as observed in Tamil Nadu" — already localised. */
  traditionLabel: string;
  /** Date line, formatted in-locale by the caller. */
  dateLabel: string;
  /** Per-tradition illustration slot. Falls back to the constellation motif. */
  art?: ReactNode;
  onOpen?: () => void;
  className?: string;
}

export function FestivalBanner({
  name,
  traditionLabel,
  dateLabel,
  art,
  onOpen,
  className,
}: FestivalBannerProps) {
  const t = useTranslations();

  const body = (
    <>
      <span aria-hidden="true" className="shrink-0">
        {art ?? <ConstellationMark />}
      </span>
      <span className="flex min-w-0 flex-col text-start">
        <span className="truncate font-serif text-h3 text-on-brand">{name}</span>
        <span className="truncate text-caption text-on-brand">{traditionLabel}</span>
        <span className="truncate text-caption text-on-brand tabular-nums">{dateLabel}</span>
      </span>
    </>
  );

  const classes = cn(
    // ceremony surface — deep navy for sky moments (§0.13)
    "flex w-full items-center gap-3 rounded-card border border-border-strong bg-brand-navy p-4 shadow-card",
    className,
  );

  if (!onOpen) return <div className={classes}>{body}</div>;
  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label={t("ui.festival.open", { name })}
      className={cn(classes, motionStandard, focusRing, "hover:shadow-sheet")}
    >
      {body}
    </button>
  );
}

/** The house constellation motif — the illustrated fallback, never a photo. */
function ConstellationMark() {
  return (
    <svg viewBox="0 0 48 48" className="h-12 w-12" role="presentation">
      <g className="stroke-gold-soft" strokeWidth="1.5" fill="none">
        <path d="M10 30 L20 14 L32 24 L38 12" strokeLinecap="round" />
      </g>
      <g className="fill-gold-soft">
        <circle cx="10" cy="30" r="2" />
        <circle cx="20" cy="14" r="2.5" />
        <circle cx="32" cy="24" r="2" />
        <circle cx="38" cy="12" r="2" />
      </g>
    </svg>
  );
}
