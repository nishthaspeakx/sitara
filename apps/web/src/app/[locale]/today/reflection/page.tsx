"use client";

/**
 * S24 Night reflection — §29.1, §28.2's evening state, §10-17's ceremony.
 *
 * ── It lives under `/today`, and that is §24.1's decision, not a filing one ─
 *
 * "Night reflection is NOT a fifth tab — it is Today's evening state, matching
 * the daily-arc mental model." So the route is `/today/reflection`, the tab
 * stays on Today, and `NightTakeover` on S14 is what leads here. A `/reflection`
 * top-level route would have been a fifth destination in a four-tab app.
 *
 * ── The date is DATA, and reading the clock here would be a bug ────────────
 *
 * §27 binds a reflection to the user's local calendar day at creation, and the
 * day comes from the Today payload — the same rule `today/sky.ts` records for
 * the night takeover and the sky band. A screen that read `new Date()` would
 * write to a different day than the brief it took over from, and every baseline
 * would depend on the hour CI ran.
 *
 * ── §29.2, which this ceremony is the most tempting place to break ─────────
 *
 * "3 prompts + day summary + tomorrow preview; ≤3 min; no streaks, no guilt."
 * There is no counter here, no progress bar toward a completed evening, and no
 * copy that treats a blank answer as an omission. Skipping is a first-class
 * answer — `ReflectionPrompt` already makes it one — and `reflection.gentle`
 * says so out loud, because an empty text box is a question a tired person can
 * still feel she failed.
 */

import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import type { ErrorEnvelope, TodayPayload } from "@sitara/schemas";

import { Button, Chip, ErrorState, Header, ReflectionPrompt, Skeleton } from "@/components/ui";
import { useRouter } from "@/i18n/navigation";
import {
  MOODS,
  loadReflection,
  saveReflection,
  type Mood,
  type Prompt,
  type Reflection,
} from "@/lib/reflection";
import { loadToday } from "@/lib/today";

type View =
  | { kind: "loading" }
  | { kind: "ready"; reflection: Reflection; payload: TodayPayload }
  | { kind: "error"; error: ErrorEnvelope };

export default function ReflectionPage() {
  const t = useTranslations();
  const locale = useLocale();
  const router = useRouter();
  const [view, setView] = useState<View>({ kind: "loading" });
  const [answers, setAnswers] = useState<Partial<Record<Prompt, string>>>({});
  const [mood, setMood] = useState<Mood | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    // The Today payload FIRST, because it carries the day this reflection
    // belongs to. Reading it from the browser would be the bug this whole
    // screen's comment header is about.
    const today = await loadToday();
    // `loadToday` also has a `loading` arm it never returns from the awaited
    // call; narrowing on `ready` rather than on `!error` is what keeps that a
    // compile-time fact instead of an assumption.
    if (today.kind !== "ready") {
      setView(
        today.kind === "error"
          ? { kind: "error", error: today.error }
          : { kind: "loading" },
      );
      return;
    }
    const date = today.payload.local_date;
    const result = await loadReflection(date, locale);
    if (!result.ok) {
      setView({ kind: "error", error: result.error });
      return;
    }
    setView({ kind: "ready", reflection: result.data, payload: today.payload });
    setAnswers(Object.fromEntries(result.data.entries.map((e) => [e.prompt, e.text])));
    setMood(result.data.mood);
  }, [locale]);

  useEffect(() => {
    void load();
  }, [load]);

  async function persist(next: Partial<Record<Prompt, string>>, nextMood: Mood | null) {
    if (view.kind !== "ready") return;
    setBusy(true);
    const result = await saveReflection(view.reflection.date, {
      locale,
      entries: next,
      mood: nextMood,
    });
    setBusy(false);
    if (result.ok) {
      setSaved(true);
      setView({ ...view, reflection: result.data });
    } else {
      setView({ kind: "error", error: result.error });
    }
  }

  return (
    // §29.5: "Night reflection: state 9 header, dimmed." The dusk treatment is
    // the theme's, applied by `data-theme` on the document — not a filter and
    // not a per-screen palette, for the reasons `today/sky.ts` records about
    // text on a fixed dark surface.
    <div data-testid="reflection" className="flex min-h-screen flex-col bg-bg-canvas">
      <Header
        variant="presence"
        titleKey="reflection.title"
        subtitleKey="reflection.intro"
        taraState="night"
        onBack={() => router.back()}
      />

      <main className="flex flex-1 flex-col gap-5 px-5 pb-10 pt-4">
        {view.kind === "loading" ? <Skeleton variant="brief" /> : null}

        {view.kind === "error" ? (
          <ErrorState error={view.error} onRetry={() => void load()} />
        ) : null}

        {view.kind === "ready" ? (
          <>
            {/* No streak, no count, nothing to break. §29.2 in one sentence,
                said before the first question rather than after the last. */}
            <p data-testid="reflection-gentle" className="text-body text-ink-muted">
              {t("reflection.gentle")}
            </p>

            {/* The ORDER is served (`prompt_order`), never assumed from the
                client's own list — two declarations of a ceremony's order are
                two things that can disagree about the shape of the ceremony. */}
            {view.reflection.prompt_order.map((prompt, index) => (
              <ReflectionPrompt
                key={prompt}
                prompt={t(`reflection.prompt.${prompt}`)}
                index={index + 1}
                total={view.reflection.prompt_order.length}
                value={answers[prompt] ?? ""}
                onChange={(value) => setAnswers((current) => ({ ...current, [prompt]: value }))}
                onSubmit={() => void persist(answers, mood)}
                onSkip={() => void persist(answers, mood)}
              />
            ))}

            <fieldset data-testid="reflection-mood" className="flex flex-col gap-2">
              <legend className="pb-2 font-serif text-h3 text-ink-primary">
                {t("reflection.mood_title")}
              </legend>
              <div className="-mx-5 flex gap-2 overflow-x-auto px-5 pb-1">
                {MOODS.map((value) => (
                  <Chip
                    key={value}
                    variant="choice"
                    selected={mood === value}
                    onClick={() => {
                      const next = mood === value ? null : value;
                      setMood(next);
                      void persist(answers, next);
                    }}
                  >
                    {t(`reflection.mood.${value}`)}
                  </Chip>
                ))}
              </div>
              {/* Optional throughout — a reflection with no mood is complete. */}
              <p className="text-caption text-ink-muted">{t("reflection.mood_skip")}</p>
            </fieldset>

            {saved ? (
              <p data-testid="reflection-saved" className="text-caption text-ink-muted">
                {t("reflection.saved")}
              </p>
            ) : null}

            <Button
              variant="primary"
              fullWidth
              loading={busy}
              data-testid="reflection-done"
              onClick={async () => {
                await persist(answers, mood);
                router.push("/today");
              }}
            >
              {t("reflection.done")}
            </Button>
          </>
        ) : null}
      </main>
    </div>
  );
}
