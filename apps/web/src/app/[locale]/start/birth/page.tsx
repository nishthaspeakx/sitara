"use client";

/**
 * S06 — birth details (§29.1 `/start/birth`, §10-6).
 *
 * Date and place here; the time and its accuracy are S07, because §10-6 makes
 * the accuracy a question in its own right rather than a checkbox beside a
 * field. Nothing is committed until S07 — the birth row is written once, whole,
 * through §13's facade.
 *
 * The place picker resolves a TIMEZONE, not just a label. §5.2 never infers a
 * zone from anywhere but the stored place, so a typed city that was never
 * chosen from the list cannot be submitted: there would be no zone, and a chart
 * computed in the wrong zone is wrong in a way nothing downstream can detect.
 */

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import {
  Button,
  Card,
  ErrorState,
  Input,
  ListRow,
  SearchField,
  SectionHeader,
  Sheet,
} from "@/components/ui";
import { patchState, searchPlaces, STEPS, useOnboarding, type Place } from "@/lib/onboarding";
import { useCloseOnBack } from "@/lib/overlay";

import { useStepCommit } from "../_step";

export default function BirthPage() {
  const t = useTranslations();
  const { birthDate, birthPlace, set } = useOnboarding();
  const { commit, busy, error, clearError } = useStepCommit(STEPS.BIRTH);
  const [query, setQuery] = useState(birthPlace?.label ?? "");
  const [results, setResults] = useState<Place[]>([]);
  const [whyOpen, setWhyOpen] = useState(false);
  useCloseOnBack(whyOpen, () => setWhyOpen(false));

  useEffect(() => {
    // A chosen place is a settled answer; re-querying it would replace the
    // resolved coordinate with a list the user has to pick from again.
    if (!query.trim() || query === birthPlace?.label) {
      setResults([]);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      const result = await searchPlaces(query, controller.signal);
      if (result.ok) setResults(result.data);
    }, 200);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query, birthPlace?.label]);

  const ready = Boolean(birthDate) && Boolean(birthPlace);

  return (
    <main className="mx-auto flex max-w-md flex-col gap-6 px-6 pb-12">
      <SectionHeader titleKey="start.birth.title" subtitleKey="start.birth.subtitle" />

      <Card as="section" className="flex flex-col gap-4">
        <Input
          kind="date"
          labelKey="start.birth.date_label"
          value={birthDate}
          max={new Date().toISOString().slice(0, 10)}
          onChange={(e) => set({ birthDate: e.target.value })}
          data-testid="birth-date"
        />

        <div className="flex flex-col gap-2">
          <SearchField
            value={query}
            onChange={(next) => {
              setQuery(next);
              // Typing after a selection clears it: the label and the resolved
              // coordinate must never disagree.
              if (birthPlace && next !== birthPlace.label) set({ birthPlace: null });
            }}
            onClear={() => {
              setQuery("");
              set({ birthPlace: null });
            }}
            labelKey="start.birth.place_label"
            placeholderKey="start.birth.place_placeholder"
          />
          <p className="text-caption text-ink-muted">{t("start.birth.place_hint")}</p>

          {results.length > 0 ? (
            <ul data-testid="place-results">
              {results.map((place) => (
                <li key={place.id ?? place.label}>
                  <ListRow
                    label={place.label}
                    detail={place.tz}
                    onClick={() => {
                      set({ birthPlace: place });
                      setQuery(place.label);
                      setResults([]);
                    }}
                  />
                </li>
              ))}
            </ul>
          ) : null}

          {query.trim() && results.length === 0 && !birthPlace ? (
            <p className="text-caption text-ink-muted" data-testid="place-empty">
              {t("start.birth.place_empty")}
            </p>
          ) : null}
        </div>
      </Card>

      {/* S06 collects, S07 writes the pair. This still commits: §24.4's resume
          reads the LOWEST unrecorded step, so a screen that advances without
          recording itself sends a returning user backwards. */}
      <Button
        fullWidth
        loading={busy}
        disabled={!ready}
        data-testid="birth-continue"
        onClick={() => void commit(() => patchState({ completed_step: STEPS.BIRTH }))}
      >
        {t("start.continue")}
      </Button>

      {error ? <ErrorState error={error} onRetry={clearError} /> : null}

      <Button variant="tertiary" onClick={() => setWhyOpen(true)}>
        {t("start.birth.why_ask")}
      </Button>

      <Sheet open={whyOpen} onClose={() => setWhyOpen(false)} titleKey="start.birth.why_ask">
        <p className="text-body text-ink-primary">{t("start.birth.why_body")}</p>
      </Sheet>
    </main>
  );
}
