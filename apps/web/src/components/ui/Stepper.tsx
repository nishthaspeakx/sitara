"use client";

/**
 * Stepper — §24.3 structure. A named, multi-step task where the user can see
 * where they are and go back: gift flow (S32), birth-detail correction (§30.2).
 * Distinct from ProgressDots, which is the anonymous onboarding indicator.
 */

import { Check } from "lucide-react";
import { useTranslations } from "next-intl";

import { ICON_STROKE, cn, type MessageKey } from "./_util";

export interface Step {
  labelKey: MessageKey;
}

export interface StepperProps {
  steps: Step[];
  /** 1-based. */
  current: number;
  /** Called with a 1-based index for any completed step. */
  onStepBack?: (step: number) => void;
  className?: string;
}

export function Stepper({ steps, current, onStepBack, className }: StepperProps) {
  const t = useTranslations();
  return (
    <ol className={cn("flex items-start gap-2", className)}>
      {steps.map((step, i) => {
        const index = i + 1;
        const done = index < current;
        const active = index === current;
        const canGoBack = done && Boolean(onStepBack);
        const marker = (
          <>
            <span
              aria-hidden="true"
              className={cn(
                "flex h-6 w-6 shrink-0 items-center justify-center rounded-portrait border text-caption",
                done && "bg-interactive-primary text-on-gold border-border-strong",
                active && "bg-surface text-ink-primary border-border-strong",
                !done && !active && "bg-surface-sunken text-ink-muted border-border-subtle",
              )}
            >
              {done ? <Check strokeWidth={ICON_STROKE} className="h-4 w-4" /> : index}
            </span>
            <span
              className={cn(
                "text-caption",
                active ? "text-ink-primary" : "text-ink-muted",
              )}
            >
              {t(step.labelKey)}
            </span>
          </>
        );
        return (
          <li
            key={step.labelKey}
            aria-current={active ? "step" : undefined}
            className="flex min-w-0 flex-1 flex-col items-center gap-1 text-center"
          >
            {canGoBack ? (
              <button
                type="button"
                onClick={() => onStepBack?.(index)}
                className="flex flex-col items-center gap-1 rounded-chip p-1 outline-none focus-visible:outline focus-visible:outline-focus focus-visible:outline-offset-focus focus-visible:outline-focus-ring focus-visible:shadow-focus"
              >
                {marker}
              </button>
            ) : (
              <span className="flex flex-col items-center gap-1 p-1">{marker}</span>
            )}
          </li>
        );
      })}
    </ol>
  );
}
