"use client";

/**
 * S09 — astrology-interest register (§29.1 `/start/interest`, §10-8).
 *
 * "believer / curious / skeptic-friendly framing choice; tunes Tara's register,
 * never the facts."
 *
 * That last clause is the whole screen. The answer becomes `profiles.density`
 * (§28.2), which changes how MANY cards a morning has and how much jargon they
 * carry — and changes no computation whatsoever. The subtitle says so in the
 * user's own language, because a screen that looked like it was choosing how
 * much astrology to believe would be selling, not asking.
 */

import { useTranslations } from "next-intl";

import { Button, Card, ErrorState, SectionHeader } from "@/components/ui";
import { patchState, STEPS, useOnboarding, type Interest } from "@/lib/onboarding";

import { useStepCommit } from "../_step";

/** §10-8's three, ordered light → full. `curious` is the skeptic-friendly end. */
const OPTIONS: Interest[] = ["curious", "balanced", "devout"];

export default function InterestPage() {
  const t = useTranslations();
  const { interest, set } = useOnboarding();
  const { commit, busy, error, clearError } = useStepCommit(STEPS.INTEREST);

  return (
    <main className="mx-auto flex max-w-md flex-col gap-6 px-6 pb-12">
      <SectionHeader titleKey="start.interest.title" subtitleKey="start.interest.subtitle" />

      <div className="flex flex-col gap-3">
        {OPTIONS.map((option) => (
          <Card
            key={option}
            tone={interest === option ? "ceremony" : "default"}
            onClick={() => set({ interest: option })}
            className="text-start"
          >
            <span
              className="flex flex-col gap-1"
              data-testid={`interest-${option}`}
              data-selected={interest === option}
            >
              <span className="font-serif text-h3 text-ink-primary">
                {t(`start.interest.option.${option}`)}
              </span>
              <span className="text-caption text-ink-muted">
                {t(`start.interest.option.${option}_help`)}
              </span>
            </span>
          </Card>
        ))}
      </div>

      <Button
        fullWidth
        loading={busy}
        disabled={!interest}
        data-testid="interest-continue"
        onClick={() =>
          void commit(() => patchState({ interest, completed_step: STEPS.INTEREST }))
        }
      >
        {t("start.continue")}
      </Button>

      {error ? <ErrorState error={error} onRetry={clearError} /> : null}
    </main>
  );
}
