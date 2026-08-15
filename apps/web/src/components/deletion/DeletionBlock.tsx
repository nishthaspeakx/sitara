"use client";

/**
 * §30.5's confirm, as one block that every scope renders.
 *
 * **`src/components/deletion/` is NOT the component library** — the same rule
 * `today/`, `ask/` and `call/` follow. §24.3 is fixed at 49 and
 * `tests/library.spec.ts` scans only `src/components/ui`. Everything here
 * composes library components.
 *
 * ── One block, four scopes, and why that is the whole design ───────────────
 *
 * §30.5's four deletions have genuinely different consequences and one shape.
 * Written per screen, they would drift: the vault's sheet would grow a "keeps"
 * line and the journal's would lose one, and the scope with the widest radius
 * would be the one whose sheet a reviewer read last.
 *
 * So the SENTENCES come from `lib/deletion-scope.ts` — asserted there, in all
 * three locales, with no two scopes sharing a key — and this file only decides
 * where they sit. A screen cannot write its own version of what a deletion
 * keeps, because there is no prop here that takes a sentence.
 *
 * The structure is §30.5's own three questions, in the order a person asks
 * them: what goes · what stays · what do I choose.
 *
 * ── The confirm button is `secondary`, deliberately ───────────────────────
 *
 * The gold fill is this app's "yes, go on", and §29.2 forbids nudging someone
 * toward a door that does not open again. The control is still full width, at
 * the shared touch-target height, and labelled with the scope's own verb —
 * findable, never pre-selected, never the prettiest thing on the sheet.
 */

import { useTranslations } from "next-intl";
import { useId, useState } from "react";

import type { ErrorEnvelope } from "@sitara/schemas";

import { Button, ErrorState } from "@/components/ui";
import { cn, touchTarget } from "@/components/ui/_util";
import { SCOPE_COPY, memoryCheckboxDefault, type DeletionScope } from "@/lib/deletion-scope";
import type { MemoryAboutMember } from "@/lib/family";

export interface DeletionChoice {
  /** §30.5's journal checkbox. */
  deleteMemories: boolean;
  /** §32.15's ticked candidates. Empty everywhere else. */
  memoryIds: string[];
}

export interface DeletionBlockProps {
  scope: DeletionScope;
  /** ICU values for the scope's own sentences — a name, and nothing more. */
  values?: Record<string, string>;
  /**
   * §32.15's LISTED candidates. Present only where the spec lists them, and
   * their presence is what turns the single checkbox into a per-row choice:
   * "about them" is a name match, so she ticks what she means rather than
   * accepting a judgement made for her.
   */
  candidates?: readonly MemoryAboutMember[];
  onConfirm: (choice: DeletionChoice) => void;
  busy?: boolean;
  error?: ErrorEnvelope | null;
  className?: string;
}

export function DeletionBlock({
  scope,
  values,
  candidates,
  onConfirm,
  busy = false,
  error,
  className,
}: DeletionBlockProps) {
  const t = useTranslations();
  const id = useId();
  const copy = SCOPE_COPY[scope];

  // §30.5 and §32.15 both make KEEPING the default, and the default IS the
  // promise the `keeps` line just made. `memoryCheckboxDefault()` is where that
  // is decided, so no screen ships its own.
  const [alsoMemories, setAlsoMemories] = useState(memoryCheckboxDefault());
  const [ticked, setTicked] = useState<readonly string[]>([]);

  const listed = candidates ?? [];
  const hasList = listed.length > 0;

  return (
    <div data-testid={`confirm-${scope}`} className={cn("flex flex-col gap-4", className)}>
      {/* (1) what goes. Every scope destroys something and says so first. */}
      <p data-testid="confirm-deletes" className="text-body text-ink-primary">
        {t(copy.deletesKey, values)}
      </p>

      {/* (2) what stays. §30.5's scopes are distinguished by what they do NOT
          touch, and a sheet listing only the damage teaches a user that
          deletion is always total — so she avoids the one that was safe. */}
      <p data-testid="confirm-keeps" className="text-body text-ink-muted">
        {t(copy.keepsKey, values)}
      </p>

      {/* (3) what she chooses, where §30.5 gives her a choice. */}
      {copy.checkboxKey && hasList ? (
        <fieldset className="flex flex-col gap-2 border-t border-border-subtle pt-3">
          <legend className="pb-2 text-caption text-ink-muted">{t(copy.checkboxKey, values)}</legend>
          {listed.map((candidate) => (
            <label
              key={candidate.memory_id}
              data-memory-id={candidate.memory_id}
              className={cn(
                "flex items-start gap-3 rounded-chip p-2 text-body text-ink-primary",
                "focus-within:outline focus-within:outline-focus focus-within:outline-offset-focus " +
                  "focus-within:outline-focus-ring",
              )}
            >
              <input
                type="checkbox"
                checked={ticked.includes(candidate.memory_id)}
                onChange={(event) =>
                  setTicked((current) =>
                    event.target.checked
                      ? [...current, candidate.memory_id]
                      : current.filter((value) => value !== candidate.memory_id),
                  )
                }
                className={cn("mt-1 h-5 w-5 shrink-0 accent-[--color-interactive-primary]")}
              />
              {/* Shown with its CONTENT: she is being asked whether to delete
                  THIS, so showing it is the entire point of "listed". */}
              <span>{candidate.content}</span>
            </label>
          ))}
        </fieldset>
      ) : null}

      {copy.checkboxKey && !hasList ? (
        <label
          htmlFor={`${id}-also`}
          className={cn(
            "flex items-start gap-3 border-t border-border-subtle pt-3 text-body text-ink-primary",
            touchTarget,
          )}
        >
          <input
            id={`${id}-also`}
            data-testid="confirm-checkbox"
            type="checkbox"
            checked={alsoMemories}
            onChange={(event) => setAlsoMemories(event.target.checked)}
            className="mt-1 h-5 w-5 shrink-0 accent-[--color-interactive-primary]"
          />
          <span>{t(copy.checkboxKey, values)}</span>
        </label>
      ) : null}

      {error ? <ErrorState error={error} /> : null}

      {/* The destructive control — see the file header for why it is
          `secondary` rather than the app's gold "yes, go on". */}
      <Button
        variant="secondary"
        fullWidth
        loading={busy}
        data-testid="confirm-submit"
        onClick={() =>
          onConfirm({
            deleteMemories: hasList ? ticked.length > 0 : alsoMemories,
            memoryIds: [...ticked],
          })
        }
      >
        {t(copy.confirmKey, values)}
      </Button>
    </div>
  );
}
