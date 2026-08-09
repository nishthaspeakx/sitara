"use client";

/**
 * S11 — life priorities (§29.1 `/start/priorities`, §24.4 "≤3 chips").
 *
 * The cap is three and it is enforced twice: here, so the interface never lets
 * a fourth be chosen, and on the server, because the ranking engine weights
 * every priority it is given and a client is not where a product rule lives.
 *
 * Reaching the cap disables the unchosen chips rather than silently ignoring a
 * tap — an unresponsive control that gives no reason is the same dead end
 * §24.6 rules out, just a small one.
 */

import { useTranslations } from "next-intl";

import { Button, Chip, ErrorState, SectionHeader } from "@/components/ui";
import { patchState, STEPS, useOnboarding } from "@/lib/onboarding";

import { useStepCommit } from "../_step";

const OPTIONS = [
  "career",
  "relationships",
  "family",
  "health",
  "money",
  "study",
  "spiritual",
  "peace",
] as const;

const MAX = 3;

export default function PrioritiesPage() {
  const t = useTranslations();
  const { priorities, set } = useOnboarding();
  const { commit, busy, error, clearError } = useStepCommit(STEPS.PRIORITIES);
  const full = priorities.length >= MAX;

  function toggle(option: string) {
    set({
      priorities: priorities.includes(option)
        ? priorities.filter((p) => p !== option)
        : full
          ? priorities
          : [...priorities, option],
    });
  }

  return (
    <main className="mx-auto flex max-w-md flex-col gap-6 px-6 pb-12">
      <SectionHeader titleKey="start.priorities.title" subtitleKey="start.priorities.subtitle" />

      <div className="flex flex-wrap gap-2" data-testid="priority-chips">
        {OPTIONS.map((option) => {
          const selected = priorities.includes(option);
          return (
            <Chip
              key={option}
              selected={selected}
              disabled={!selected && full}
              onClick={() => toggle(option)}
            >
              {t(`start.priorities.option.${option}`)}
            </Chip>
          );
        })}
      </div>

      <p className="text-caption text-ink-muted" aria-live="polite" data-testid="priority-count">
        {t("start.priorities.hint", { count: priorities.length })}
      </p>

      <Button
        fullWidth
        loading={busy}
        disabled={priorities.length === 0}
        data-testid="priorities-continue"
        onClick={() =>
          void commit(() => patchState({ priorities, completed_step: STEPS.PRIORITIES }))
        }
      >
        {t("start.continue")}
      </Button>

      {error ? <ErrorState error={error} onRetry={clearError} /> : null}
    </main>
  );
}
