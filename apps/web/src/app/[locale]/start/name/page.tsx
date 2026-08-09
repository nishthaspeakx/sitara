"use client";

/**
 * S10 — name & numerology (§29.1 `/start/name`, §22.10, §10-9).
 *
 * §22.10: "Chaldean values are defined over the **Latin transliteration of the
 * name as spoken**. At onboarding, non-Latin name entry triggers an automatic
 * ISO 15919-based transliteration shown to the user for confirmation ("We read
 * your name as 'Lakshmi' — correct?"); the confirmed Latin form is stored as
 * the canonical numerology input."
 *
 * Two consequences the screen has to honour:
 *
 * * **The confirmation is not optional and not implicit.** A Devanagari name
 *   cannot be committed until its Latin reading has been accepted or corrected.
 *   §22.10 calls the confirmed form canonical, and a canonical value nobody
 *   confirmed is a guess with a certificate.
 * * **The moolank is computed by the engine, not here.** It is a §5.3 fact.
 *   This screen sends a name and renders a number it was given.
 */

import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button, Card, ErrorState, Input, Modal, SectionHeader } from "@/components/ui";
import { patchState, STEPS, useOnboarding } from "@/lib/onboarding";
import { useCloseOnBack } from "@/lib/overlay";

import { useStepCommit } from "../_step";

/** Latin, digits, spaces and the joiners a name legitimately carries. */
const IS_LATIN = /^[A-Za-z][A-Za-z\s.'-]*$/;

export default function NamePage() {
  const t = useTranslations();
  const { displayName, latinName, set } = useOnboarding();
  const { commit, busy, error, clearError } = useStepCommit(STEPS.NAME);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [draftLatin, setDraftLatin] = useState("");
  useCloseOnBack(confirmOpen, () => setConfirmOpen(false));

  const trimmed = displayName.trim();
  const alreadyLatin = IS_LATIN.test(trimmed);
  const confirmed = alreadyLatin ? trimmed : latinName.trim();

  function onContinue() {
    if (!trimmed) return;
    if (alreadyLatin) {
      // The name is already the spelling the Chaldean table reads. Asking a
      // Latin-script user to confirm their own spelling is a step for nothing.
      void commit(() =>
        patchState({
          display_name: trimmed,
          latin_name: trimmed,
          completed_step: STEPS.NAME,
        }),
      );
      return;
    }
    // §22.10's confirm step. The server transliterates; until that endpoint
    // exists the user supplies the reading, which is the same contract from the
    // screen's side and never a guessed value from ours.
    setDraftLatin(latinName);
    setConfirmOpen(true);
  }

  return (
    <main className="mx-auto flex max-w-md flex-col gap-6 px-6 pb-12">
      <SectionHeader titleKey="start.name.title" subtitleKey="start.name.subtitle" />

      <Card as="section">
        <Input
          kind="text"
          labelKey="start.name.name_label"
          value={displayName}
          autoComplete="given-name"
          onChange={(e) => set({ displayName: e.target.value })}
          data-testid="name-input"
        />
      </Card>

      <Button
        fullWidth
        loading={busy}
        disabled={!trimmed}
        data-testid="name-continue"
        onClick={onContinue}
      >
        {t("start.continue")}
      </Button>

      {error ? <ErrorState error={error} onRetry={clearError} /> : null}

      <Modal
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        titleKey="start.name.transliteration.title"
        confirmKey="start.name.transliteration.confirm"
        cancelKey="start.name.transliteration.edit"
        onConfirm={() => {
          const value = draftLatin.trim();
          if (!IS_LATIN.test(value)) return;
          set({ latinName: value });
          setConfirmOpen(false);
          void commit(() =>
            patchState({
              display_name: trimmed,
              latin_name: value,
              completed_step: STEPS.NAME,
            }),
          );
        }}
      >
        <p className="text-body text-ink-primary">
          {t("start.name.transliteration.body", { latin: draftLatin || trimmed })}
        </p>
        <Input
          kind="text"
          labelKey="start.name.transliteration.latin_label"
          value={draftLatin}
          onChange={(e) => setDraftLatin(e.target.value)}
          className="mt-4"
          data-testid="latin-input"
        />
      </Modal>

      {confirmed ? (
        <p className="sr-only" data-testid="latin-name">
          {confirmed}
        </p>
      ) : null}
    </main>
  );
}
