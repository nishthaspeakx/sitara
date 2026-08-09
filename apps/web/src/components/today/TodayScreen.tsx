"use client";

/**
 * S14 Today — §28.2's anatomy, in §28.2's order.
 *
 * The order is the specification, not a layout preference, so it is written
 * once here as a flat sequence rather than distributed across nested
 * components:
 *
 *   1 header (date + tithi, sky, story ring, settings)
 *   2 Tara's line          — always present
 *   3 the core card        — always the single dominant card
 *   4 the practical strip  — colour · number · favourable · caution
 *   5 contextual cards     — engine-ranked, max 4 visible, "more" expands
 *   6 the panchang row
 *   7 night: the whole tab transforms after 20:00
 *
 * **"Nothing competes with the core card — enforced by layout, not judgement."**
 * That is §28.2's own sentence and it is why `CoreCard` is the only place in
 * this tree that renders `emphasis="core"`: dominance is a property of the
 * component that can be counted (`[data-emphasis="core"]` appears exactly once,
 * asserted per variant in `today-screens.spec.ts`), not a rule a reviewer has
 * to hold in their head while reading JSX.
 *
 * §32.1's precedence lives in `src/lib/today-variant.ts` and arrives here as a
 * resolved `TodayChrome`. This component never asks "is there a festival AND
 * two banners already" — it renders what the rule decided.
 */

import type { MorningModule, TodayModule, TodayPayload } from "@sitara/schemas";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { BriefCard, Button, Card, ConfidenceChip, TabBar } from "@/components/ui";
import { VISIBLE_CONTEXTUAL, type TodayChrome } from "@/lib/today-variant";

import { BannerStack } from "./BannerStack";
import { BriefTimePicker } from "./BriefTimePicker";
import { FirstSession } from "./FirstSession";
import { NightTakeover } from "./NightTakeover";
import { PanchangRow } from "./PanchangRow";
import { PracticalStrip } from "./PracticalStrip";
import { SkyHeader } from "./SkyHeader";
import { TarasLine } from "./TarasLine";
import { TrustSheetHost } from "./TrustSheetHost";

/**
 * §28.2 item (3): "THE day's theme from her chart". `personal_chart_theme` is
 * that module; `energy_of_day` stands in when the chart half was not in hand,
 * which is the degraded morning's core card (§7.1's "panchang + one chart
 * theme"). Order is preference, not fallback-to-anything: if neither is
 * present there is no core card, and §5.3 says that is the correct answer.
 */
const CORE_PREFERENCE: MorningModule[] = ["personal_chart_theme", "energy_of_day"];

/** §28.2 item (4)'s four, in the order the strip reads them. */
const PRACTICAL: MorningModule[] = ["colour", "number", "favourable_window", "caution_window"];

/** Item (6). `PanchangRow` renders this one; see its own note for why. */
const PANCHANG_MODULE: MorningModule = "moon_nakshatra_note";

export interface TodayScreenProps {
  payload: TodayPayload;
  chrome: TodayChrome;
  onSelectTab?: (tab: string) => void;
  onEditBriefTime?: () => void;
  /** §28.2's Free variant CTA → /you/subscription. */
  onOpenPlans?: () => void;
  /**
   * §28.2's offline variant: "practical strip marked 'as of [time]'".
   *
   * Passed down rather than read here, because the age of a cached payload is
   * known only by whatever read it out of the cache — a screen that stamped
   * "now" on it would be making a promise about data it did not fetch.
   */
  cachedAt?: string;
  /** Story/dev hook: expands the "more" list without a click. */
  defaultExpanded?: boolean;
}

export function TodayScreen({
  payload,
  chrome,
  onSelectTab,
  onEditBriefTime,
  onOpenPlans,
  cachedAt,
  defaultExpanded = false,
}: TodayScreenProps) {
  const t = useTranslations();
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [trustFor, setTrustFor] = useState<TodayModule | null>(null);
  const [briefTimeOpen, setBriefTimeOpen] = useState(false);

  const byId = new Map(payload.modules.map((m) => [m.module, m]));
  const core = CORE_PREFERENCE.map((id) => byId.get(id)).find(Boolean) ?? null;
  const practical = PRACTICAL.map((id) => byId.get(id)).filter(Boolean) as TodayModule[];

  // Everything the anatomy has not already placed. Order is preserved from the
  // payload, which is §34.3's canonical order — the ranking engine decided
  // WHICH, the spec decides in what sequence they read.
  const placed = new Set<MorningModule>([
    ...(core ? [core.module] : []),
    ...practical.map((m) => m.module),
    PANCHANG_MODULE,
  ]);
  const contextual = payload.modules.filter((m) => !placed.has(m.module));
  const visible = expanded ? contextual : contextual.slice(0, VISIBLE_CONTEXTUAL);

  return (
    <div
      data-testid="today"
      data-variant={chrome.variant}
      data-band={chrome.band}
      data-density={payload.density}
      className="flex min-h-screen flex-col bg-bg-canvas"
    >
      <SkyHeader payload={payload} chrome={chrome} />
      <BannerStack payload={payload} chrome={chrome} cachedAt={cachedAt} />

      <main className="flex flex-1 flex-col gap-5 px-5 pb-24 pt-2">
        {/* (2) — always present, in every variant, with or without a brief. */}
        <TarasLine payload={payload} chrome={chrome} />

        {chrome.night ? (
          /* (7) §28.2: "the whole tab transforms after 20:00 — dusk tokens,
             reflection CTA replaces core card position". The reflection prompt
             takes the dominant slot, so no core card renders and the
             one-dominant-card rule still holds by construction. */
          <NightTakeover payload={payload} />
        ) : payload.state.first_session ? (
          /* §28.2's first-session variant IS the empty state ("empty
             (pre-first-brief) = first-session variant") — a recap, a promise
             and the brief-time control, never a generic EmptyState. */
          <FirstSession
            payload={payload}
            onEditBriefTime={() => {
              setBriefTimeOpen(true);
              onEditBriefTime?.();
            }}
          />
        ) : (
          <>
            {/* (3) the one dominant card */}
            {core ? (
              <CoreCard
                card={core}
                locked={chrome.locked}
                festivalAccent={
                  chrome.festivalAccent ? payload.state.festival?.name : undefined
                }
                onWhyThis={() => setTrustFor(core)}
              />
            ) : null}

            {/* §7.1's degrade, said out loud (§28.2). Below the core card, so
                the honest note explains the short screen rather than
                introducing it as a warning. */}
            {payload.status === "verified_core_cards" || payload.status === "failed" ? (
              <div className="flex flex-col items-start gap-2">
                <p data-testid="degraded-note" className="text-body text-ink-muted">
                  {t("today.degraded")}
                </p>
                {/* The brief's own state, beside the sentence that explains it.
                    §34.7: a degraded state is an honest limit, never an alarm —
                    `tradition_based_general` is a neutral fill and the spec
                    forbids reaching for caution or danger colour here. */}
                {payload.confidence ? (
                  <span data-testid="today-confidence" data-state={payload.confidence}>
                    <ConfidenceChip state={payload.confidence} />
                  </span>
                ) : null}
              </div>
            ) : null}

            {/* §28.2's Free variant: "locked personal cards with single calm
                unlock CTA (never guilt)". ONE CTA, once, below the card it
                explains — not a banner, not per card, and with no countdown or
                loss framing (§29.2). The panchang stays open above it, which
                is the "generic panchang" half of the same sentence. */}
            {chrome.locked ? (
              <Card measure>
                <div data-testid="unlock-cta" className="flex flex-col items-start gap-2">
                  <h3 className="font-serif text-h3 text-ink-primary">
                    {t("today.locked.title")}
                  </h3>
                  <p className="text-body text-ink-muted">{t("today.locked.body")}</p>
                  <Button variant="secondary" onClick={onOpenPlans}>
                    {t("today.locked.action")}
                  </Button>
                </div>
              </Card>
            ) : null}

            {/* (4) one row, compact chips */}
            {practical.length ? <PracticalStrip modules={practical} /> : null}

            {/* (5) max 4 visible, "more" expands */}
            {visible.length ? (
              <section data-testid="contextual-cards" className="flex flex-col gap-3">
                {visible.map((card) => (
                  // The `data-module` hook lives on a wrapper, not on
                  // `BriefCard`: the component destructures its declared props
                  // and drops the rest, so an attribute passed to it would
                  // typecheck and then silently never reach the DOM.
                  <div key={card.module} data-module={card.module}>
                    <BriefCard
                      module={card.module}
                      factLine={card.text}
                      confidence={card.confidence}
                      locked={chrome.locked}
                      onWhyThis={() => setTrustFor(card)}
                    />
                  </div>
                ))}
                {contextual.length > VISIBLE_CONTEXTUAL ? (
                  <button
                    type="button"
                    data-testid="today-more"
                    onClick={() => setExpanded((v) => !v)}
                    className="self-start rounded-chip px-2 py-1 text-caption text-ink-primary underline decoration-gold underline-offset-4"
                  >
                    {t(expanded ? "today.less" : "today.more")}
                  </button>
                ) : null}
              </section>
            ) : null}

            {/* (6) */}
            <PanchangRow
              payload={payload}
              row={byId.get(PANCHANG_MODULE)}
              onWhyThis={() => {
                const row = byId.get(PANCHANG_MODULE);
                if (row) setTrustFor(row);
              }}
            />
          </>
        )}
      </main>

      <TrustSheetHost module={trustFor} onClose={() => setTrustFor(null)} />
      <BriefTimePicker
        open={briefTimeOpen}
        value={payload.state.brief_time}
        onClose={() => setBriefTimeOpen(false)}
      />
      <TabBar active="today" onSelect={(tab) => onSelectTab?.(tab)} />
    </div>
  );
}

/**
 * §28.2 item (3), and the one component allowed to be visually dominant.
 *
 * Kept in this file rather than its own because the dominance rule is a
 * property of the SCREEN — "nothing competes with the core card" is only
 * checkable where the siblings are visible.
 */
function CoreCard({
  card,
  locked,
  festivalAccent,
  onWhyThis,
}: {
  card: TodayModule;
  locked: boolean;
  festivalAccent?: string;
  onWhyThis: () => void;
}) {
  const t = useTranslations();
  return (
    <div data-testid="today-core" className="flex flex-col gap-2">
      {/* §32.1: a festival that lost its banner slot "renders as the core-card
          accent instead" — never dropped. */}
      {festivalAccent ? (
        <p data-testid="festival-accent" className="text-caption text-ink-muted">
          {t("today.festival_accent", { name: festivalAccent })}
        </p>
      ) : null}
      <div data-module={card.module} data-emphasis="core">
        <BriefCard
          module={card.module}
          factLine={card.text}
          confidence={card.confidence}
          locked={locked}
          emphasis="core"
          onWhyThis={onWhyThis}
        />
      </div>
    </div>
  );
}
