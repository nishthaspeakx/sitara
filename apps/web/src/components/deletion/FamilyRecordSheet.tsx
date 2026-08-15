"use client";

/**
 * §32.15 and §45, on ONE sheet — the non-destructive option first.
 *
 * ── Why this is one sheet and not two ─────────────────────────────────────
 *
 * §32.15: "'In memory of' conversion offered as the alternative on the same
 * sheet." §45.3: "The two are offered together on one sheet, and the
 * non-destructive one is presented first."
 *
 * This sheet appears at exactly one moment: someone is looking at the record of
 * a person who has died. Two separate sheets behind two separate controls would
 * mean the gentle one is found only by a user who already knew it existed —
 * which, at that moment, is nobody. So the order is not layout. It is read from
 * `FAMILY_SHEET_ORDER`, which `tests/deletion-scope.spec.ts` asserts, so a tidy
 * reflow cannot quietly put the deletion on top.
 *
 * ── The direction of danger is inverted in the upper half ─────────────────
 *
 * Everywhere else in §30.5 the drift to fear is a sheet promising LESS damage
 * than it does. Here the upper half promises none at all, and §45.2 makes that
 * true by construction — one field, no cascade. A conversion that quietly
 * removed something would be a bereaved user losing her mother's birth chart
 * because she chose the gentle option, and nobody audits for it because nobody
 * expects the gentle option to take anything. Hence three sentences rather than
 * one: what stays, what changes, and that it can be undone.
 */

import { useTranslations } from "next-intl";

import type { ErrorEnvelope } from "@sitara/schemas";

import { Button, Divider } from "@/components/ui";
import {
  FAMILY_SHEET_ORDER,
  MEMORIAL_COPY,
  SCOPE_COPY,
  type FamilySheetSection,
} from "@/lib/deletion-scope";
import { Sheet } from "@/components/ui";
import type { FamilyMember, MemoryAboutMember } from "@/lib/family";

import { DeletionBlock, type DeletionChoice } from "./DeletionBlock";

export interface FamilyRecordSheetProps {
  open: boolean;
  onClose: () => void;
  member: FamilyMember;
  /** §32.15's listed candidates, read before this sheet renders. */
  candidates: readonly MemoryAboutMember[];
  onMemorial: (state: "living" | "in_memory") => void;
  onDelete: (choice: DeletionChoice) => void;
  busy?: boolean;
  error?: ErrorEnvelope | null;
}

export function FamilyRecordSheet({
  open,
  onClose,
  member,
  candidates,
  onMemorial,
  onDelete,
  busy,
  error,
}: FamilyRecordSheetProps) {
  const t = useTranslations();
  const values = { name: member.name };
  const inMemory = member.memorial_state === "in_memory";

  const sections: Record<FamilySheetSection, React.ReactNode> = {
    memorial: (
      <section key="memorial" data-testid="memorial-section" className="flex flex-col gap-3">
        <h3 className="font-serif text-h3 text-ink-primary">
          {t(inMemory ? MEMORIAL_COPY.revertTitleKey : MEMORIAL_COPY.titleKey, values)}
        </h3>

        {inMemory ? (
          <>
            <p data-testid="memorial-revert-body" className="text-body text-ink-primary">
              {t(MEMORIAL_COPY.revertBodyKey, values)}
            </p>
            <Button variant="primary" fullWidth data-testid="memorial-revert" loading={busy}
              onClick={() => onMemorial("living")}>
              {t(MEMORIAL_COPY.revertKey, values)}
            </Button>
          </>
        ) : (
          <>
            <p data-testid="memorial-body" className="text-body text-ink-primary">
              {t(MEMORIAL_COPY.bodyKey, values)}
            </p>
            {/* What survives. First, and in the reading colour rather than the
                muted one — on this sheet it is the most important sentence. */}
            <p data-testid="memorial-keeps" className="text-body text-ink-primary">
              {t(MEMORIAL_COPY.keepsKey, values)}
            </p>
            {/* §45.2's single behavioural change, named. Copy that promised
                only survival would be false the first morning a birthday did
                not arrive. */}
            <p data-testid="memorial-reminders" className="text-body text-ink-muted">
              {t(MEMORIAL_COPY.remindersKey, values)}
            </p>
            {/* §45.2: reversible, because a wrong tap that week must not be
                another loss. */}
            <p data-testid="memorial-reversible" className="text-caption text-ink-muted">
              {t(MEMORIAL_COPY.reversibleKey, values)}
            </p>
            {/* The gentle option carries the gold. The deletion below does not
                — §29.2 forbids nudging toward the door that does not reopen. */}
            <Button variant="primary" fullWidth data-testid="memorial-confirm" loading={busy}
              onClick={() => onMemorial("in_memory")}>
              {t(MEMORIAL_COPY.confirmKey, values)}
            </Button>
          </>
        )}
      </section>
    ),

    delete: (
      <section key="delete" data-testid="delete-section" className="flex flex-col gap-3">
        <Divider />
        {/* The bridge. §45.3 keeps BOTH paths available — a member who is
            already `in_memory` may still be removed, with the same radius, and
            hiding this once the gentle state is set would trap a user who
            converted by mistake and genuinely wants the record gone. */}
        <p className="text-caption text-ink-muted">{t(MEMORIAL_COPY.orDeleteKey, values)}</p>
        <h3 className="font-serif text-h3 text-ink-primary">
          {t(SCOPE_COPY.family_member.titleKey, values)}
        </h3>
        <DeletionBlock
          scope="family_member"
          values={values}
          candidates={candidates}
          onConfirm={onDelete}
          busy={busy}
          error={error}
        />
      </section>
    ),
  };

  return (
    <Sheet
      open={open}
      onClose={onClose}
      titleKey={MEMORIAL_COPY.sheetTitleKey}
      titleValues={values}
    >
      <div data-testid="family-record-sheet" className="flex flex-col gap-5">
        {/* The ORDER is data (§45.3), not the order these happen to be
            written in — so a reflow cannot change which option she meets. */}
        {FAMILY_SHEET_ORDER.map((section) => sections[section])}
      </div>
    </Sheet>
  );
}
