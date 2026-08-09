"use client";

/**
 * ConfidenceChip — §24.3 / §34.7. ALL FIVE state treatments:
 *
 *   verified          gold outline
 *   verified_limited  soft-gold fill
 *   approximate       neutral dotted outline
 *   tradition_general neutral fill
 *   cannot_calculate  muted-ink outline + info glyph
 *
 * §34.7 is explicit that Approximate and Cannot-calculate are included and that
 * NEITHER uses caution or danger colours. Honest limits are not warnings — a
 * chip is never alarming (§9, no fear-selling). The lint enforces the colour
 * half of that rule; this comment is the reason.
 */

import { Info } from "lucide-react";
import { useTranslations } from "next-intl";

import { ICON_STROKE, cn, type ConfidenceState } from "./_util";

const TREATMENT: Record<ConfidenceState, string> = {
  verified: "border-solid border-gold bg-transparent text-ink-primary",
  verified_limited: "border-solid border-border-subtle bg-gold-soft text-on-gold",
  approximate: "border-dotted border-border-strong bg-transparent text-ink-primary",
  tradition_general: "border-solid border-border-subtle bg-surface-sunken text-ink-primary",
  cannot_calculate: "border-solid border-ink-muted bg-transparent text-ink-muted",
};

export interface ConfidenceChipProps {
  state: ConfidenceState;
  /** Renders the one-line explanation beside the label. */
  withDescription?: boolean;
  className?: string;
}

export function ConfidenceChip({ state, withDescription = false, className }: ConfidenceChipProps) {
  const t = useTranslations();
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-chip border px-3 py-1 text-caption",
        TREATMENT[state],
        className,
      )}
    >
      {state === "cannot_calculate" ? (
        <Info aria-hidden="true" strokeWidth={ICON_STROKE} className="h-4 w-4 shrink-0" />
      ) : null}
      <span className="font-medium">{t(`ui.confidence.${state}`)}</span>
      {/* the description INHERITS the treatment's text colour — ink-muted on the
          soft-gold fill is 3.33:1 in light and 1.70:1 at night, so the emphasis
          split is carried by weight, not by a second colour */}
      {withDescription ? <span>{t(`ui.confidence.${state}_desc`)}</span> : null}
    </span>
  );
}
