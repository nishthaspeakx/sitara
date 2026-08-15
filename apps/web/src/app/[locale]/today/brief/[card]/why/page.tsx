"use client";

/**
 * S15 — the Why-this sheet (§29.1, §30.4), as a route.
 *
 * This is the trust thesis made visible, so it is worth being exact about what
 * it does and does not show.
 *
 * **The three layers, in §30.4's own order.** `TrustSheet` renders them:
 * (1) the plain-language reason; (2) the sources row plus the ConfidenceChip;
 * (3) a "see the details" expander carrying the specifics — "Nakshatra ·
 * Rohini", "Rahu Kaal · 09:00–10:30". Layer 3 IS the fact snapshots behind the
 * card, read out of their values by `presenter._detail` on the server.
 *
 * **Fact IDs are not among them, and cannot be.** §30.4: "fact-IDs remain
 * internal (logs/admin) and never render to users". That is structural in three
 * places rather than remembered in one — `TodayTrust` has no field an id could
 * travel in, `TrustSheet` has no prop that could hold one, and the composer's
 * markers are stripped server-side by the chat pipeline's own
 * `strip_citations`. This page therefore has nothing to filter.
 *
 * **Why a route and not only the inline sheet.** Today already opens the sheet
 * in place — that is what makes §30.4's "≤1 tap" true. The route exists so the
 * sheet is linkable and survives a reload: a correction notice, a support
 * conversation or a deep link (§28.1) needs somewhere to point, and "open Today
 * and tap the third card" is not a destination. The card renders underneath, so
 * arriving by link looks like arriving by tap.
 *
 * A card id that is not on today's brief is an honest miss, not a 404: the
 * brief changes every morning, and yesterday's link is a stale reference rather
 * than a wrong address.
 */

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useTranslations } from "next-intl";

import { MORNING_MODULES, type MorningModule } from "@sitara/schemas";

import { BriefCard, Card, ErrorState, Header, Skeleton, TrustSheet } from "@/components/ui";
import { useRouter } from "@/i18n/navigation";
import { loadToday, type TodayView } from "@/lib/today";

export default function WhyThisPage() {
  const t = useTranslations();
  const router = useRouter();
  const params = useParams();
  const [view, setView] = useState<TodayView>({ kind: "loading" });

  // §34.3's enum is the gate: a path segment is user input, and a card id the
  // ranking engine may not emit is not a card at all.
  const raw = String(params?.card ?? "");
  const card = (MORNING_MODULES as readonly string[]).includes(raw)
    ? (raw as MorningModule)
    : null;

  useEffect(() => {
    let cancelled = false;
    void loadToday().then((next) => {
      if (!cancelled) setView(next);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // Named `entry`, not `module`: Next forbids the latter as a binding, and the
  // rule is right — a shadowed `module` in a client component is a subtle way
  // to break the bundler.
  const entry =
    view.kind === "ready" && card
      ? (view.payload.modules.find((m) => m.module === card) ?? null)
      : null;

  const back = () => router.push("/today");

  return (
    <div data-testid="why" data-card={card ?? "unknown"} className="flex min-h-app flex-col bg-bg-canvas">
      <Header variant="titled" titleKey="ui.trust.title" onBack={back} />

      <main className="flex flex-1 flex-col gap-5 px-5 pb-10 pt-4">
        {view.kind === "loading" ? <Skeleton variant="brief" /> : null}

        {view.kind === "error" ? (
          <ErrorState error={view.error} onRetry={() => router.refresh()} />
        ) : null}

        {/* The card the question is about, so arriving by link reads the same
            as arriving by tap. No "Why this?" affordance on it — you are
            already there. */}
        {entry ? (
          <div data-module={entry.module}>
            <BriefCard
              module={entry.module}
              factLine={entry.text}
              confidence={entry.confidence}
            />
          </div>
        ) : null}

        {view.kind === "ready" && !entry ? (
          <Card measure>
            <p data-testid="why-missing" className="text-body text-ink-muted">
              {t("today.why.missing")}
            </p>
          </Card>
        ) : null}
      </main>

      {/* Open from the first frame — the sheet IS the page. `defaultExpanded`
          because a reader who navigated here asked for the details; the
          expander is a progressive disclosure on Today, not a second question
          to answer on the screen dedicated to answering it. */}
      <TrustSheet
        open={entry !== null}
        onClose={back}
        plainLanguage={entry?.trust.plain ?? ""}
        confidence={entry?.confidence ?? "verified"}
        sourceState={entry?.confidence === "verified" ? "default" : "single"}
        detailLines={entry?.trust.details ?? []}
        defaultExpanded
      />
    </div>
  );
}
