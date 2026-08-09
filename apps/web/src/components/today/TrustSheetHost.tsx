"use client";

/**
 * §30.4: "every astrological claim reachable to a Trust Sheet in ≤1 tap".
 *
 * One host for the whole screen rather than a sheet per card — the sheet is
 * modal, so there is only ever one, and holding the open module in `TodayScreen`
 * keeps "which card asked" in the same place as "which cards exist".
 *
 * The three layers arrive already rendered from the API (`presenter.py`). This
 * component composes no sentences and resolves no keys against fact data,
 * because §30.4's fact-IDs are internal: `TrustSheet` has no prop that could
 * carry one, `TodayTrust` has no field that could carry one, and this file has
 * nothing to strip.
 */

import type { TodayModule } from "@sitara/schemas";

import { TrustSheet } from "@/components/ui";

export function TrustSheetHost({
  module,
  onClose,
}: {
  module: TodayModule | null;
  onClose: () => void;
}) {
  return (
    <TrustSheet
      open={module !== null}
      onClose={onClose}
      plainLanguage={module?.trust.plain ?? ""}
      confidence={module?.confidence ?? "verified"}
      sourceState={module?.confidence === "verified" ? "default" : "single"}
      detailLines={module?.trust.details ?? []}
    />
  );
}
