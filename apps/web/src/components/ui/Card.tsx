"use client";

/**
 * Card — §24.3 structure. The reading surface everything else sits on.
 * `measure` caps the line length at 65 characters (§0.13, whitespace is luxury).
 */

import type { ReactNode } from "react";

import { cn, focusRing, motionStandard } from "./_util";

export type CardTone = "default" | "sunken" | "ceremony";

const TONE: Record<CardTone, string> = {
  default: "bg-surface border-border-subtle",
  sunken: "bg-surface-sunken border-border-subtle",
  // deep navy for sky/ceremony moments (§0.13)
  ceremony: "bg-brand-navy border-border-strong text-on-brand",
};

export interface CardProps {
  tone?: CardTone;
  /** Cap the content at the 65ch reading measure. */
  measure?: boolean;
  /** Renders the card as a button; the whole surface becomes the target. */
  onClick?: () => void;
  as?: "article" | "section" | "div" | "li";
  children: ReactNode;
  className?: string;
}

export function Card({
  tone = "default",
  measure = false,
  onClick,
  as: Tag = "article",
  children,
  className,
}: CardProps) {
  const classes = cn(
    "rounded-card border p-4 shadow-card",
    TONE[tone],
    measure && "max-w-reading",
    className,
  );

  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        className={cn(classes, "w-full text-start", motionStandard, focusRing, "hover:shadow-sheet")}
      >
        {children}
      </button>
    );
  }
  return <Tag className={classes}>{children}</Tag>;
}
