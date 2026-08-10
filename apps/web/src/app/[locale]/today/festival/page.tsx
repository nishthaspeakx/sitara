"use client";

/**
 * S17 — today's observance (§29.1, `/today/festival`), where the §32.1 festival
 * banner leads.
 *
 * **Tradition-correct or absent.** §28.2 requires the festival surface to be
 * "tradition-correct", and §2.4 that "a vendor's English festival name never
 * reaches a user". Both are settled upstream: `today_state.festival_from`
 * refuses to raise a banner for a festival it cannot name in the user's
 * language, so a festival that reaches this screen is one we can name, dated by
 * a stated reckoning. This page names that reckoning rather than leaving it
 * implicit — amanta and purnimanta disagree about which day a festival falls
 * on, and a date with no calendar beside it is a claim we have not qualified.
 *
 * **Nothing is composed here.** The observance sentence is the
 * `festival_observance` module and the practice line is `spiritual_practice`,
 * both written by the engine from facts and cited before they left the server
 * (§5.3). This screen arranges; it does not write.
 */

import { useEffect, useState } from "react";
import { useFormatter, useTranslations } from "next-intl";

import type { MorningModule } from "@sitara/schemas";

import {
  BriefCard,
  Card,
  EmptyState,
  ErrorState,
  FestivalBanner,
  Header,
  Skeleton,
} from "@/components/ui";
import { useRouter } from "@/i18n/navigation";
import { loadToday, type TodayView } from "@/lib/today";

/** What the day's observance is made of, in reading order. */
const OBSERVANCE: MorningModule[] = ["festival_observance", "spiritual_practice"];

export default function FestivalPage() {
  const t = useTranslations();
  const format = useFormatter();
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

  const festival = view.kind === "ready" ? view.payload.state.festival : null;
  const cards =
    view.kind === "ready"
      ? OBSERVANCE.map((id) => view.payload.modules.find((m) => m.module === id)).filter(Boolean)
      : [];

  return (
    <div data-testid="festival" className="flex min-h-screen flex-col bg-bg-canvas">
      <Header variant="titled" titleKey="today.festival.title" onBack={() => router.back()} />

      <main className="flex flex-1 flex-col gap-5 px-5 pb-10 pt-4">
        {view.kind === "loading" ? <Skeleton variant="brief" /> : null}

        {view.kind === "error" ? (
          <ErrorState error={view.error} onRetry={() => router.refresh()} />
        ) : null}

        {view.kind === "ready" ? (
          festival ? (
            <>
              <div data-testid="festival-banner">
                <FestivalBanner
                  name={festival.name}
                  traditionLabel={festival.tradition_label}
                  dateLabel={format.dateTime(new Date(festival.date_label), {
                    day: "numeric",
                    month: "long",
                  })}
                />
              </div>

              {/* §5.2: amanta and purnimanta place the same festival on
                  different days. Stating which one dated this is the difference
                  between a fact and an assertion. */}
              {festival.tradition_label ? (
                <p data-testid="festival-tradition" className="text-caption text-ink-muted">
                  {t("today.festival.tradition", { tradition: festival.tradition_label })}
                </p>
              ) : null}

              {cards.map((card) => (
                <div key={card!.module} data-module={card!.module}>
                  <BriefCard
                    module={card!.module}
                    factLine={card!.text}
                    confidence={card!.confidence}
                  />
                </div>
              ))}

              {cards.length === 0 ? (
                // Named, dated, and nothing more to say — which happens when the
                // observance card lost the density cut. Better than an invented
                // paragraph about a festival (§5.3).
                <Card measure>
                  <p className="text-body text-ink-muted">{t("today.festival.practice")}</p>
                </Card>
              ) : null}
            </>
          ) : (
            <div data-testid="festival-empty" className="flex flex-1 items-center justify-center">
              <EmptyState id="saved_guidance" />
            </div>
          )
        ) : null}
      </main>
    </div>
  );
}
