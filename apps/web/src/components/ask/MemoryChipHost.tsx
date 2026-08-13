"use client";

/**
 * §32.4's consent chip, in the thread.
 *
 * The rule this file exists to keep: **no chip, no memory.** The offer carries
 * two equal-weight controls (`MemoryChip` enforces that shape), and nothing is
 * written until one is tapped — the API's `MemoryStore.create` takes a consent
 * record in its signature, so there is no path that stores without one.
 *
 * **Types 7–9 re-confirm their wording before saving** (§32.4: mood pattern,
 * health-adjacent, work/finance). The server sets `requires_reconfirmation`;
 * this shows Tara's paraphrase in an editable field first, because a mood or a
 * money worry she wrote down badly is worse than one she never kept. It is not
 * a second confirmation dialog — the user edits the sentence that will be
 * stored.
 */

import { useTranslations } from "next-intl";
import { useState } from "react";
import type { MemoryChipOffer } from "@sitara/schemas";

import { Button, MemoryChip } from "@/components/ui";
import { cn, focusRing, touchTarget } from "@/components/ui/_util";

export type ChipDecision = "accepted" | "declined";

export function MemoryChipHost({
  offer,
  decision,
  onAccept,
  onDecline,
}: {
  offer: MemoryChipOffer;
  decision: ChipDecision | null;
  onAccept: (summary: string) => void;
  onDecline: () => void;
}) {
  const t = useTranslations();
  // A BARE identifier, not `offer.type`. `i18n-lint` matches the literal
  // template text against `dynamic-keys.json`; `${offer.type}` is a template
  // it cannot expand and therefore cannot verify (the same rule
  // `ui.module.${module}` follows on the Today screen).
  const { type } = offer;
  const [wording, setWording] = useState(offer.summary);
  const [confirming, setConfirming] = useState(false);

  if (decision) {
    return <MemoryChip state={decision} summary={offer.summary} />;
  }

  if (confirming) {
    return (
      <div
        data-testid="memory-reconfirm"
        className="flex flex-col gap-2 rounded-chip border border-dashed border-border-strong bg-surface p-3"
      >
        <p className="text-caption text-ink-muted">{t(`ui.memory.type.${type}`)}</p>
        <label className="sr-only" htmlFor="memory-wording">
          {t("ui.memory.offer")}
        </label>
        <input
          id="memory-wording"
          value={wording}
          onChange={(e) => setWording(e.target.value)}
          className={cn(
            "rounded-chip border border-border-subtle bg-bg-canvas px-3 text-body text-ink-primary",
            touchTarget,
            focusRing,
          )}
        />
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" onClick={() => onAccept(wording.trim())}>
            {t("ui.memory.accept")}
          </Button>
          <Button variant="tertiary" onClick={onDecline}>
            {t("ui.memory.decline")}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div data-testid="memory-chip" className="flex flex-col gap-1">
      <MemoryChip
        state="offer"
        summary={offer.summary}
        onAccept={() =>
          offer.requires_reconfirmation ? setConfirming(true) : onAccept(offer.summary)
        }
        onDecline={onDecline}
      />
      <span className="ps-1 text-caption text-ink-muted">
        {t(`ui.memory.type.${type}`)}
      </span>
    </div>
  );
}
