"use client";

/**
 * §30.5's confirm as a sheet of its own — the memory and journal-entry scopes.
 *
 * The family scope does NOT use this: §45.3 requires its deletion to share a
 * sheet with the non-destructive alternative, and to be presented second. That
 * is `FamilyRecordSheet`, which renders the same `DeletionBlock` in its lower
 * half — so the two paths cannot drift in what they promise, only in what they
 * are offered beside.
 */

import type { ErrorEnvelope } from "@sitara/schemas";

import { Sheet } from "@/components/ui";
import { SCOPE_COPY, type DeletionScope } from "@/lib/deletion-scope";

import { DeletionBlock, type DeletionChoice } from "./DeletionBlock";

export interface ConfirmDeleteSheetProps {
  scope: Exclude<DeletionScope, "family_member">;
  open: boolean;
  onClose: () => void;
  /** ICU values for the scope's sentences. */
  values?: Record<string, string>;
  onConfirm: (choice: DeletionChoice) => void;
  busy?: boolean;
  error?: ErrorEnvelope | null;
}

export function ConfirmDeleteSheet({
  scope,
  open,
  onClose,
  values,
  onConfirm,
  busy,
  error,
}: ConfirmDeleteSheetProps) {
  return (
    <Sheet
      open={open}
      onClose={onClose}
      titleKey={SCOPE_COPY[scope].titleKey}
      titleValues={values}
    >
      <DeletionBlock
        scope={scope}
        values={values}
        onConfirm={onConfirm}
        busy={busy}
        error={error}
      />
    </Sheet>
  );
}
