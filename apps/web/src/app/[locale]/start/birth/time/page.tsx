"use client";

/**
 * S07 — birth-time accuracy (§29.1 `/start/birth/time`, §10-6, §5.4).
 *
 * §10-6's four honest options: "exact / ±30min / morning-afternoon-evening-night
 * / unknown — drives the confidence system honestly."
 *
 * The screen's real job is making "I don't know" a comfortable answer. A
 * majority of users genuinely do not know their birth time, and an interface
 * that treats that as a failure produces a guessed time — which is worse than
 * no time, because §5.4 can be honest about an absence and cannot be honest
 * about a fabrication it was never told about.
 *
 * This is where the whole birth row is written, through §13's facade: date and
 * place from S06, time and accuracy from here, one call.
 */

import { useTranslations } from "next-intl";
import { useEffect } from "react";

import {
  Button,
  Card,
  ConfidenceChip,
  ErrorState,
  Input,
  SectionHeader,
  SegmentedControl,
} from "@/components/ui";
import { useRouter } from "@/i18n/navigation";
import {
  putBirth,
  STEP_ROUTES,
  STEPS,
  useOnboarding,
  type PartOfDay,
  type TimeAccuracy,
} from "@/lib/onboarding";

import { useStepCommit } from "../../_step";

const OPTIONS: TimeAccuracy[] = ["exact", "approximate", "part_of_day", "unknown"];
const PARTS: PartOfDay[] = ["morning", "afternoon", "evening", "night"];

/** §5.4's table, previewed on the screen that decides it. Honesty is the
 *  product here, so the consequence of the answer is shown WITH the answer. */
const CONFIDENCE_PREVIEW: Record<TimeAccuracy, string> = {
  exact: "verified",
  approximate: "approximate",
  part_of_day: "approximate",
  unknown: "verified_limited_birth_data",
};

export default function BirthTimePage() {
  const t = useTranslations();
  const router = useRouter();
  const { birthDate, birthPlace, timeAccuracy, birthTime, partOfDay, set } = useOnboarding();
  const { commit, busy, error, clearError } = useStepCommit(STEPS.BIRTH_TIME);

  // Arriving here without S06's answers means a resume landed mid-pair. Back to
  // the question that has to be answered first — never a blank form (§28.1).
  //
  // In an effect, not in the render body: navigating during render mutates the
  // router while React is rendering, which React treats as a side effect in the
  // wrong phase and which loops if the guard condition never changes.
  const incomplete = !birthDate || !birthPlace;
  useEffect(() => {
    if (incomplete) router.replace(STEP_ROUTES[STEPS.BIRTH]!);
  }, [incomplete, router]);
  if (incomplete) return null;

  const needsClock = timeAccuracy === "exact" || timeAccuracy === "approximate";
  const ready =
    timeAccuracy === "unknown" ||
    (timeAccuracy === "part_of_day" && partOfDay !== null) ||
    (needsClock && Boolean(birthTime));

  return (
    <main className="mx-auto flex max-w-md flex-col gap-6 px-6 pb-12">
      <SectionHeader titleKey="start.birth_time.title" subtitleKey="start.birth_time.subtitle" />

      <Card as="section" className="flex flex-col gap-3">
        {OPTIONS.map((option) => (
          <label
            key={option}
            className="flex cursor-pointer items-start gap-3 rounded-card p-2"
            data-testid={`accuracy-${option}`}
          >
            <input
              type="radio"
              name="time-accuracy"
              className="mt-1 accent-interactive-primary"
              checked={timeAccuracy === option}
              onChange={() => set({ timeAccuracy: option })}
            />
            <span className="flex flex-col">
              <span className="text-body text-ink-primary">
                {t(`start.birth_time.option.${option}`)}
              </span>
              <span className="text-caption text-ink-muted">
                {t(`start.birth_time.option.${option}_help`)}
              </span>
            </span>
          </label>
        ))}
      </Card>

      {needsClock ? (
        <Card as="section">
          <Input
            kind="time"
            labelKey="start.birth_time.time_label"
            value={birthTime}
            onChange={(e) => set({ birthTime: e.target.value })}
            data-testid="birth-time"
          />
        </Card>
      ) : null}

      {timeAccuracy === "part_of_day" ? (
        <SegmentedControl
          labelKey="start.birth_time.window_label"
          segments={PARTS.map((part) => ({
            value: part,
            labelKey: `start.birth_time.part.${part}`,
          }))}
          value={partOfDay ?? ""}
          onChange={(value) => set({ partOfDay: value as PartOfDay })}
        />
      ) : null}

      {timeAccuracy ? (
        <div className="flex justify-start" data-testid="accuracy-preview">
          <ConfidenceChip
            state={CONFIDENCE_PREVIEW[timeAccuracy] as never}
            withDescription
          />
        </div>
      ) : null}

      <Button
        fullWidth
        loading={busy}
        disabled={!ready}
        data-testid="birth-time-continue"
        onClick={() =>
          void commit(() =>
            putBirth({
              date: birthDate,
              place: birthPlace,
              time_accuracy: timeAccuracy as TimeAccuracy,
              // §5.3: only send a time when one was actually given. "unknown"
              // and "part_of_day" send none, and the facade decides what the
              // engine gets — never this screen.
              time: needsClock ? birthTime : null,
              part_of_day: timeAccuracy === "part_of_day" ? partOfDay : null,
            }),
          )
        }
      >
        {t("start.continue")}
      </Button>

      {error ? <ErrorState error={error} onRetry={clearError} /> : null}
    </main>
  );
}
