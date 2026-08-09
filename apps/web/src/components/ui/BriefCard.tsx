"use client";

/**
 * BriefCard — §24.3 Sitara-specific. ONE master with 17 module variants
 * (§7.1/§34.3 closed set): icon slot, fact line, "Why this?" affordance.
 *
 * `module` is typed `MorningModule` from @sitara/schemas, so a card cannot be
 * rendered for an id the ranking engine is not allowed to emit.
 *
 * The fact line is passed in as already-rendered text. Per §5.3 the LLM never
 * computes it and per §30.4 the fact IDs behind it never reach the user — the
 * card's job is to make the sentence reachable to a TrustSheet in ≤1 tap.
 */

import type { MorningModule } from "@sitara/schemas";
import {
  Apple,
  BellRing,
  Briefcase,
  CalendarClock,
  CircleDashed,
  Compass,
  Flame,
  Hash,
  Heart,
  Moon,
  Palette,
  ShieldAlert,
  Sparkles,
  Sunrise,
  Target,
  Users,
  Wind,
} from "lucide-react";
import { useTranslations } from "next-intl";
import type { ComponentType, ReactNode } from "react";

import { Card } from "./Card";
import { ConfidenceChip } from "./ConfidenceChip";
import { ICON_STROKE, cn, focusRing, motionStandard, type ConfidenceState } from "./_util";

/** One glyph per module. Astrology glyphs are custom and Jyotish-lead reviewed
 *  (§24.7); the Lucide base carries the everyday ones. */
const MODULE_ICON: Record<MorningModule, ComponentType<{ strokeWidth?: number; className?: string }>> = {
  energy_of_day: Sunrise,
  personal_chart_theme: Compass,
  moon_nakshatra_note: Moon,
  colour: Palette,
  number: Hash,
  favourable_window: CalendarClock,
  caution_window: ShieldAlert,
  priorities: Target,
  what_to_avoid: Wind,
  food_and_drink: Apple,
  work: Briefcase,
  relationship: Heart,
  family_reminder: Users,
  festival_observance: Flame,
  goal_check: CircleDashed,
  spiritual_practice: Sparkles,
  tomorrow_prep_teaser: BellRing,
};

export interface BriefCardProps {
  module: MorningModule;
  /** The guidance sentence, already localised and grounded in engine facts. */
  factLine: string;
  confidence?: ConfidenceState;
  /** Opens the TrustSheet — §30.4 requires this to be ≤1 tap from any claim. */
  onWhyThis?: () => void;
  /** Free-tier locked variant (§28.2). */
  locked?: boolean;
  /** Today's core card renders larger; the rest are contextual. */
  emphasis?: "core" | "contextual";
  /** Per-guidance actions (RatingTap) rendered in the footer. */
  actions?: ReactNode;
  className?: string;
}

export function BriefCard({
  module,
  factLine,
  confidence,
  onWhyThis,
  locked = false,
  emphasis = "contextual",
  actions,
  className,
}: BriefCardProps) {
  const t = useTranslations();
  const Icon = MODULE_ICON[module];

  return (
    <Card
      measure
      className={cn("flex flex-col gap-3", emphasis === "core" && "shadow-sheet", className)}
    >
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className="mt-1 shrink-0 rounded-portrait bg-surface-sunken p-2 text-ink-muted"
        >
          <Icon strokeWidth={ICON_STROKE} />
        </span>
        <div className="flex min-w-0 flex-col gap-1">
          <h3
            className={cn(
              "font-serif text-ink-primary",
              emphasis === "core" ? "text-h2" : "text-h3",
            )}
          >
            {t(`ui.module.${module}`)}
          </h3>
          {locked ? (
            <p className="text-body text-ink-muted">{t("ui.brief.locked")}</p>
          ) : (
            <p className={cn("text-ink-primary", emphasis === "core" ? "text-body" : "text-body")}>
              {factLine}
            </p>
          )}
        </div>
      </div>

      {!locked && (confidence || onWhyThis || actions) ? (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            {confidence ? <ConfidenceChip state={confidence} /> : null}
            {onWhyThis ? (
              <button
                type="button"
                data-testid="why-this"
                onClick={onWhyThis}
                className={cn(
                  "rounded-chip px-2 py-1 text-caption text-ink-primary underline decoration-gold underline-offset-4",
                  motionStandard,
                  focusRing,
                )}
              >
                {t("ui.why_this")}
              </button>
            ) : null}
          </div>
          {actions}
        </div>
      ) : null}
    </Card>
  );
}
