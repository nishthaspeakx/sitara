"use client";

/**
 * TrustSheet — §24.3 / §34.7 / §30.4. THE canonical component; the earlier
 * WhyThisSheet name is retired (§34.7).
 *
 * Three layers, in this order:
 *   1. plain language   — "Today the Moon moves through your 10th house — work
 *                          themes rise. Your birth time is exact, so this is precise."
 *   2. the sources row  — VerifiedSourceRow + ConfidenceChip
 *   3. "see the details" expander — nakshatra/tithi/transit specifics in
 *                          READABLE TERMS, for enthusiasts
 *
 * §30.4, load-bearing: **fact-IDs remain internal (logs/admin) and never render
 * to users.** This component therefore has no prop that can carry one. It takes
 * sentences the caller has already rendered from the fact snapshot; it cannot
 * be handed an ID to print, and a screen that tries has to notice.
 */

import { ChevronDown } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { ConfidenceChip } from "./ConfidenceChip";
import { Sheet } from "./Sheet";
import { VerifiedSourceRow, type SourceState } from "./VerifiedSourceRow";
import { ICON_STROKE, cn, focusRing, motionStandard, type ConfidenceState } from "./_util";

export interface TrustSheetProps {
  open: boolean;
  onClose: () => void;
  /** Layer 1 — the plain-language reason, already localised by the caller. */
  plainLanguage: string;
  /** Layer 2 */
  confidence: ConfidenceState;
  sourceState?: SourceState;
  /**
   * Layer 3 — readable detail lines ("Moon in Purva Bhadrapada until 14:20").
   * Never fact IDs: §30.4 keeps those internal.
   */
  detailLines?: string[];
  /** Story/test hook. */
  defaultExpanded?: boolean;
}

export function TrustSheet({
  open,
  onClose,
  plainLanguage,
  confidence,
  sourceState = "default",
  detailLines = [],
  defaultExpanded = false,
}: TrustSheetProps) {
  const t = useTranslations();
  const [expanded, setExpanded] = useState(defaultExpanded);

  return (
    <Sheet open={open} onClose={onClose} titleKey="ui.trust.title">
      <div className="flex flex-col gap-4">
        {/* layer 1 */}
        <p className="max-w-reading text-body text-ink-primary">{plainLanguage}</p>

        {/* layer 2 */}
        <div className="flex flex-col gap-2 rounded-card bg-surface-sunken p-3">
          <VerifiedSourceRow state={sourceState} />
          <ConfidenceChip state={confidence} withDescription />
        </div>

        {/* layer 3 */}
        {detailLines.length > 0 ? (
          <div className="flex flex-col gap-2">
            <button
              type="button"
              aria-expanded={expanded}
              onClick={() => setExpanded((v) => !v)}
              className={cn(
                "flex items-center justify-between gap-2 rounded-chip border border-border-subtle px-3 py-3 text-start text-body text-ink-primary",
                motionStandard,
                focusRing,
                "hover:bg-surface-sunken",
              )}
            >
              <span>{expanded ? t("ui.trust.details_hide") : t("ui.trust.details_show")}</span>
              <ChevronDown
                aria-hidden="true"
                strokeWidth={ICON_STROKE}
                className={cn("shrink-0", motionStandard, expanded && "rotate-180")}
              />
            </button>
            {expanded ? (
              <ul className="flex flex-col gap-2 ps-4">
                {detailLines.map((line) => (
                  <li key={line} className="list-disc text-body text-ink-muted">
                    {line}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
      </div>
    </Sheet>
  );
}
