"use client";

/**
 * S08 — current city (§29.1 `/start/city`, §10-7, §30.1).
 *
 * §30.1's universal pattern: **explain → invite → system prompt → honour the
 * answer.** "No system permission dialog ever fires without its explainer sheet
 * (S43) shown first, in-locale, stating the concrete value and the skip path."
 *
 * So the geolocation prompt is never reached by tapping the primary control —
 * it is reached by tapping through the explainer. And §30.1's location rule adds
 * one more thing: "asked at city step with manual entry equally prominent".
 * Equally prominent is a layout requirement, not a sentiment: the manual field
 * is on the screen from the first frame, not behind a "no thanks".
 */

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import {
  Button,
  Card,
  ErrorState,
  ListRow,
  SearchField,
  SectionHeader,
  Sheet,
} from "@/components/ui";
import { patchState, searchPlaces, STEPS, useOnboarding, type Place } from "@/lib/onboarding";
import { useCloseOnBack } from "@/lib/overlay";

import { useStepCommit } from "../_step";

export default function CityPage() {
  const t = useTranslations();
  const { city, set } = useOnboarding();
  const { commit, busy, error, clearError } = useStepCommit(STEPS.CITY);
  const [query, setQuery] = useState(city?.label ?? "");
  const [results, setResults] = useState<Place[]>([]);
  const [explainerOpen, setExplainerOpen] = useState(false);
  useCloseOnBack(explainerOpen, () => setExplainerOpen(false));

  useEffect(() => {
    if (!query.trim() || query === city?.label) {
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
  }, [query, city?.label]);

  /**
   * Only ever called from inside the explainer sheet — that is what makes the
   * §30.1 ordering structural rather than a convention someone can forget.
   *
   * A denial is honoured and never re-prompted (browsers will not show the
   * dialog again anyway); the manual field below is the stated no-permission
   * path, and §30.1 requires every permissioned feature to have one.
   */
  function askForLocation() {
    setExplainerOpen(false);
    if (!("geolocation" in navigator)) return;
    navigator.geolocation.getCurrentPosition(
      async (position) => {
        const result = await searchPlaces(
          `${position.coords.latitude.toFixed(2)},${position.coords.longitude.toFixed(2)}`,
        );
        // The gazetteer resolves cities by name; a coordinate lookup lands with
        // the §5.2 Google resolver. Until then this falls through to manual
        // entry rather than storing an unresolved point — §5.3 again: a place
        // without a verified zone produces confidently-wrong timings.
        const first = result.ok ? result.data[0] : undefined;
        if (first) {
          set({ city: first });
          setQuery(first.label);
        }
      },
      () => undefined,
      { maximumAge: 600_000, timeout: 8000 },
    );
  }

  return (
    <main className="mx-auto flex max-w-md flex-col gap-6 px-6 pb-12">
      <SectionHeader titleKey="start.city.title" subtitleKey="start.city.subtitle" />

      <Card as="section" className="flex flex-col gap-4">
        <Button
          variant="secondary"
          fullWidth
          onClick={() => setExplainerOpen(true)}
          data-testid="city-use-location"
        >
          {t("start.city.use_location")}
        </Button>

        <div className="flex flex-col gap-2">
          <SearchField
            value={query}
            onChange={(next) => {
              setQuery(next);
              if (city && next !== city.label) set({ city: null });
            }}
            onClear={() => {
              setQuery("");
              set({ city: null });
            }}
            labelKey="start.city.manual_label"
            placeholderKey="start.city.manual_placeholder"
          />
          {results.length > 0 ? (
            <ul data-testid="city-results">
              {results.map((place) => (
                <li key={place.id ?? place.label}>
                  <ListRow
                    label={place.label}
                    detail={place.tz}
                    onClick={() => {
                      set({ city: place });
                      setQuery(place.label);
                      setResults([]);
                    }}
                  />
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </Card>

      <Button
        fullWidth
        loading={busy}
        disabled={!city}
        data-testid="city-continue"
        onClick={() =>
          void commit(() => patchState({ city, completed_step: STEPS.CITY }))
        }
      >
        {t("start.continue")}
      </Button>

      {error ? <ErrorState error={error} onRetry={clearError} /> : null}

      {/* S43 — §30.1's permission explainer. One component, three contents;
          this is the location one. */}
      <Sheet
        open={explainerOpen}
        onClose={() => setExplainerOpen(false)}
        titleKey="start.city.permission.title"
      >
        <p className="text-body text-ink-primary">{t("start.city.permission.body")}</p>
        <div className="mt-4 flex flex-col gap-2">
          <Button fullWidth onClick={askForLocation} data-testid="location-allow">
            {t("start.city.permission.allow")}
          </Button>
          <Button variant="tertiary" fullWidth onClick={() => setExplainerOpen(false)}>
            {t("start.city.permission.skip")}
          </Button>
        </div>
      </Sheet>
    </main>
  );
}
