"use client";

/**
 * S16 — the day's timings (§29.1, `/today/timings`), where §28.2 item (6)'s
 * panchang row leads.
 *
 * Two spec rules shape this screen more than anything else:
 *
 * **§29.4's dataviz rules.** "Timing bars use time-of-day x-axis with
 * now-marker … no pie charts". `TimingBar` is that component and it already
 * carries the harder half — auspicious and care are never encoded by colour
 * alone, so every band has a glyph and a legend label and reads the same in
 * greyscale.
 *
 * **§30.2: the place is never implied.** A timing is computed FOR somewhere,
 * and a screen that showed windows without saying where would be wrong for
 * every traveller. The payload carries `place_label` from the profile's
 * `brief_place`; when it is absent the label is omitted rather than guessed
 * from the timezone — a zone is not a place, and "Asia/Kolkata" is not a city
 * anyone chose.
 *
 * The now-marker comes from the payload's `local_time`, not the browser clock:
 * the same reason the night takeover does (§28.2's variants are pinned by the
 * brief, and a baseline must not depend on when CI ran).
 */

import { useEffect, useState } from "react";

import { EmptyState, ErrorState, Header, PanchangStrip, Skeleton, TimingBar } from "@/components/ui";
import type { TimingQuality as BarQuality } from "@/components/ui";
import { useRouter } from "@/i18n/navigation";
import { loadToday, type TodayView } from "@/lib/today";
import { useTranslations } from "next-intl";

/**
 * The engine's vocabulary → the bar's.
 *
 * `inauspicious` is a fact about the sky; "care" is what a person should be
 * told (§29.2 forbids fear-selling, and §24.2 keeps this band amber, never
 * red). The mapping lives here rather than on the wire so the honest word and
 * the kind word stay separately owned.
 */
const BAND_QUALITY: Record<string, BarQuality> = {
  auspicious: "favourable",
  inauspicious: "care",
  neutral: "neutral",
};

function toMinutes(localTime: string): number {
  const [h, m] = localTime.split(":").map(Number);
  return (h || 0) * 60 + (m || 0);
}

export default function TimingsPage() {
  const t = useTranslations();
  const router = useRouter();
  const [view, setView] = useState<TodayView>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    void loadToday().then((next) => {
      if (!cancelled) setView(next);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div data-testid="timings" className="flex min-h-screen flex-col bg-bg-canvas">
      <Header variant="titled" titleKey="today.timings.title" onBack={() => router.back()} />

      <main className="flex flex-1 flex-col gap-5 px-5 pb-10 pt-4">
        {view.kind === "loading" ? <Skeleton variant="brief" /> : null}

        {view.kind === "error" ? (
          <ErrorState error={view.error} onRetry={() => router.refresh()} />
        ) : null}

        {view.kind === "ready" ? (
          view.payload.timings.length ? (
            <>
              <TimingBar
                bands={view.payload.timings.map((timing) => ({
                  label: timing.name,
                  startMinute: timing.starts_minute,
                  endMinute: timing.ends_minute,
                  quality: BAND_QUALITY[timing.quality] ?? "neutral",
                  range: timing.range,
                }))}
                nowMinute={toMinutes(view.payload.local_time)}
                placeLabel={view.payload.place_label ?? undefined}
              />
              {/* §29.2: the windows are described, never ranked into a verdict
                  about the day. A "best time" would be advice the engine did
                  not compute. */}
              <p className="text-caption text-ink-muted">{t("today.timings.legend")}</p>

              {view.payload.panchang.length ? (
                <PanchangStrip
                  entries={view.payload.panchang.map((entry) => ({
                    labelKey: entry.label_key,
                    value: entry.value,
                  }))}
                />
              ) : null}
            </>
          ) : (
            /* The panchang cell was cold. §24.6's designed empty state, with the
               honest sentence — not an empty axis. */
            <div data-testid="timings-empty" className="flex flex-1 items-center justify-center">
              <EmptyState id="saved_guidance" />
            </div>
          )
        ) : null}
      </main>
    </div>
  );
}
