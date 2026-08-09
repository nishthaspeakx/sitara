"use client";

/**
 * S05 — consent (§29.1 `/start/consent`, §10-5, §13).
 *
 * "layered, in-locale: essential processing; birth-data sensitivity explained
 * in one honest paragraph; memory consent DEFERRED to first chip (contextual);
 * voice processing consent at first voice use; marketing separate, default off."
 *
 * So there are THREE cards here, not five. Memory and voice consent are
 * deliberately absent: §32.4 makes memory consent a chip at the moment Tara
 * offers to remember something, and §30.1 makes voice consent the first voice
 * action. Collecting either here would be asking for permission to do something
 * the user has not yet been shown — which is how consent becomes a formality.
 */

import { useState } from "react";
import { useTranslations } from "next-intl";

import { Button, Card, ConsentRow, ErrorState, SectionHeader, Sheet } from "@/components/ui";
import { postConsents, STEPS } from "@/lib/onboarding";
import { useCloseOnBack } from "@/lib/overlay";

import { useStepCommit } from "../_step";

/** `required` is §10-5's "essential processing" — explained, never pre-ticked
 *  as a trick. Marketing is separate and defaults OFF (§10-5, §29.2). */
const ITEMS = [
  { id: "essential", required: true, defaultGranted: true },
  { id: "birth_data", required: true, defaultGranted: true },
  { id: "marketing", required: false, defaultGranted: false },
] as const;

export default function ConsentPage() {
  const t = useTranslations();
  const { commit, busy, error, clearError } = useStepCommit(STEPS.CONSENT);
  const [granted, setGranted] = useState<Record<string, boolean>>(
    Object.fromEntries(ITEMS.map((i) => [i.id, i.defaultGranted])),
  );
  const [policyOpen, setPolicyOpen] = useState(false);
  useCloseOnBack(policyOpen, () => setPolicyOpen(false));

  return (
    <main className="mx-auto flex max-w-md flex-col gap-6 px-6 pb-12">
      <SectionHeader titleKey="start.consent.title" subtitleKey="start.consent.subtitle" />

      <Card as="section" className="flex flex-col gap-2">
        {ITEMS.map((item) => (
          <ConsentRow
            key={item.id}
            labelKey={`start.consent.item.${item.id}.label`}
            descriptionKey={`start.consent.item.${item.id}.body`}
            granted={granted[item.id] ?? false}
            required={item.required}
            onChange={
              item.required
                ? undefined
                : (next) => setGranted((g) => ({ ...g, [item.id]: next }))
            }
            onOpenPolicy={() => setPolicyOpen(true)}
          />
        ))}
      </Card>

      <Button
        fullWidth
        loading={busy}
        data-testid="consent-continue"
        onClick={() =>
          void commit(() =>
            // Only what was actually granted is recorded. The ledger is legal
            // (§13); writing a marketing consent the user left off would be a
            // false record, not a harmless default.
            postConsents(ITEMS.filter((i) => granted[i.id]).map((i) => i.id)),
          )
        }
      >
        {t("start.continue")}
      </Button>

      {error ? <ErrorState error={error} onRetry={clearError} /> : null}

      <Sheet open={policyOpen} onClose={() => setPolicyOpen(false)} titleKey="start.consent.title">
        <p className="text-body text-ink-primary">{t("start.consent.item.birth_data.body")}</p>
      </Sheet>
    </main>
  );
}
