"use client";

/**
 * ProgressDots — §24.3 structure. The onboarding step indicator (§24.4: every
 * onboarding screen carries progress dots and back always works).
 *
 * The dots are decorative; the step position is announced in words so it is
 * never colour-only or shape-only information.
 */

import { useTranslations } from "next-intl";

import { cn } from "./_util";

/** §24.4 — the onboarding flow is 13 screens. */
export const ONBOARDING_STEPS = 13;

export interface ProgressDotsProps {
  current: number;
  total?: number;
  className?: string;
}

export function ProgressDots({ current, total = ONBOARDING_STEPS, className }: ProgressDotsProps) {
  const t = useTranslations();
  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <div className="flex items-center gap-2" aria-hidden="true">
        {Array.from({ length: total }, (_, i) => (
          <span
            key={i}
            className={cn(
              "h-1 w-1 rounded-portrait",
              i + 1 === current
                ? "bg-interactive-primary"
                : i + 1 < current
                  ? "bg-border-strong"
                  : "bg-border-subtle",
            )}
          />
        ))}
      </div>
      <p className="sr-only" aria-live="polite">
        {t("ui.progress.step", { current, total })}
      </p>
    </div>
  );
}
