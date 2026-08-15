"use client";

/**
 * One Journal artefact, as a row.
 *
 * **`src/components/journal/` is NOT the component library** — §24.3 is fixed
 * at 49 and `tests/library.spec.ts` scans only `src/components/ui`. This
 * composes `Card`, `Chip` and `IconButton`.
 *
 * Two things the shape enforces:
 *
 * **A row whose source is gone is still a row.** §30.5 makes the Journal a
 * VIEW: `preview` is rendered from wherever the artefact actually lives, so it
 * can be `null`. Dropping the row would erase the fact that the day happened;
 * the honest thing is to keep the row and say the original is not there. §24.6
 * forbids dead ends, and a silently shorter list is a quieter version of one.
 *
 * **The delete control is not the row's own tap target.** Opening an entry and
 * destroying it are one pixel apart otherwise, and one of them does not undo.
 */

import { Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";

import { Card, Chip, IconButton } from "@/components/ui";
import { ICON_STROKE } from "@/components/ui/_util";
import type { JournalEntry } from "@/lib/journal";

export interface EntryRowProps {
  entry: JournalEntry;
  onOpen?: () => void;
  /** Absent where this surface does not offer deletion (search results). */
  onDelete?: () => void;
}

export function EntryRow({ entry, onOpen, onDelete }: EntryRowProps) {
  const t = useTranslations();
  // A BARE identifier: `i18n-lint` matches the literal template text against
  // `dynamic-keys.json`, and `${entry.artefact_type}` is one it cannot expand
  // and therefore cannot verify. Same rule as `ui.module.${module}`.
  const type = entry.artefact_type;

  return (
    // The data attributes sit on the `li` rather than on `Card`: `Card` takes a
    // closed prop set and spreads nothing, which is what keeps a caller from
    // smuggling arbitrary DOM onto a library component.
    <li data-testid="journal-entry" data-artefact={type} data-ref={entry.ref}>
      <Card className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <Chip>{t(`journal.type.${type}`)}</Chip>
        <div className="flex items-center gap-1">
          {entry.saved ? (
            <span className="text-caption text-ink-muted">{t("journal.saved")}</span>
          ) : null}
          {onDelete ? (
            <IconButton
              variant="plain"
              labelKey="journal.entry_delete"
              data-testid="entry-delete"
              onClick={onDelete}
              icon={<Trash2 strokeWidth={ICON_STROKE} />}
            />
          ) : null}
        </div>
      </div>

      {entry.preview ? (
        <button
          type="button"
          onClick={onOpen}
          disabled={!onOpen}
          className="text-start text-body text-ink-primary disabled:cursor-default"
        >
          {entry.preview}
        </button>
      ) : (
        // The artefact is gone and the row says so. Never a blank row, and
        // never a row quietly removed from the day it belonged to.
        <p data-testid="entry-source-gone" className="text-body text-ink-muted">
          {t("journal.source_gone")}
        </p>
      )}
      </Card>
    </li>
  );
}
