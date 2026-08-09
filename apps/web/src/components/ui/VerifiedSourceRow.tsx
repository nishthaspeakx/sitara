"use client";

/**
 * VerifiedSourceRow — §24.3 / §34.7 / §30.4. Three states:
 *
 *   default   "computed from your chart · verified against 2 sources ✓"
 *   single    one source only — said plainly, not hidden
 *   disputed  the providers disagree; §5-D adjudication is running
 *
 * The disputed state is deliberately calm: it uses the neutral border, not the
 * caution colour. A disagreement between almanacs is not a warning to the user.
 */

import { CheckCheck, Check, GitCompareArrows } from "lucide-react";
import { useTranslations } from "next-intl";
import type { ComponentType } from "react";

import { ICON_STROKE, cn } from "./_util";

export type SourceState = "default" | "single" | "disputed";

const ICON: Record<SourceState, ComponentType<{ strokeWidth?: number; className?: string }>> = {
  default: CheckCheck,
  single: Check,
  disputed: GitCompareArrows,
};

const KEY: Record<SourceState, string> = {
  default: "ui.source.verified_two",
  single: "ui.source.single",
  disputed: "ui.source.disputed",
};

export interface VerifiedSourceRowProps {
  state?: SourceState;
  className?: string;
}

export function VerifiedSourceRow({ state = "default", className }: VerifiedSourceRowProps) {
  const Icon = ICON[state];
  const t = useTranslations();
  return (
    <p
      className={cn(
        "flex items-center gap-2 text-caption",
        state === "disputed" ? "text-ink-muted" : "text-ink-primary",
        className,
      )}
    >
      <Icon aria-hidden="true" strokeWidth={ICON_STROKE} className="h-4 w-4 shrink-0" />
      <span>{t(KEY[state])}</span>
    </p>
  );
}
