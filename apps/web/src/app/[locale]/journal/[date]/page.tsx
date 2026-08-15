"use client";

/**
 * S22 Journal day — §29.1 `/journal/[date]`.
 *
 * **A day with nothing in it is a DAY, not a 404.** The API says so
 * (`journal/router.py`: "an empty day is a day (§24.6: no dead ends)") and this
 * screen has to agree, because the timeline links to dates and a calendar will
 * eventually link to every date there is. A 404 on a quiet Tuesday would be the
 * app telling someone she failed to have a life that day.
 *
 * The route is `[date]` and its sibling is the static `search`. Next resolves a
 * static segment before a dynamic one, so `/journal/search` reaches S23 rather
 * than arriving here as a date — `tests/journal-routes.spec.ts` asserts it,
 * because the failure mode is a search screen that becomes an invalid-date
 * error the day someone reorders the folder.
 */

import { useTranslations } from "next-intl";
import { useLocale } from "next-intl";
import { useCallback, useEffect, useState } from "react";
import { use } from "react";

import type { ErrorEnvelope } from "@sitara/schemas";

import { ConfirmDeleteSheet } from "@/components/deletion/ConfirmDeleteSheet";
import { EntryRow } from "@/components/journal/EntryRow";
import { EmptyState, ErrorState, Header, Skeleton } from "@/components/ui";
import { useRouter } from "@/i18n/navigation";
import { formatLongDate } from "@/lib/dates";
import {
  deleteArtefact,
  loadDay,
  sourceMessageIds,
  type JournalDay,
  type JournalEntry,
} from "@/lib/journal";

type View =
  | { kind: "loading" }
  | { kind: "ready"; day: JournalDay }
  | { kind: "error"; error: ErrorEnvelope };

export default function JournalDayPage({
  params,
}: {
  params: Promise<{ date: string }>;
}) {
  const { date } = use(params);
  const t = useTranslations();
  const locale = useLocale();
  const router = useRouter();
  const [view, setView] = useState<View>({ kind: "loading" });
  const [pending, setPending] = useState<JournalEntry | null>(null);
  const [busy, setBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<ErrorEnvelope | null>(null);

  const refresh = useCallback(async () => {
    const result = await loadDay(date);
    setView(result.ok ? { kind: "ready", day: result.data } : { kind: "error", error: result.error });
  }, [date]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <div data-testid="journal-day" data-date={date} className="flex min-h-screen flex-col bg-bg-canvas">
      {/* The title is user-facing DATA — a formatted date — so it goes through
          `title`, not `titleKey`. Same convention `FamilyCard` uses for a name. */}
      <Header variant="titled" title={formatLongDate(date, locale)} onBack={() => router.back()} />

      <main className="flex flex-1 flex-col gap-3 px-5 pb-10 pt-4">
        {view.kind === "loading" ? <Skeleton variant="list" /> : null}

        {view.kind === "error" ? (
          <ErrorState error={view.error} onRetry={() => void refresh()} />
        ) : null}

        {view.kind === "ready" && view.day.entries.length === 0 ? (
          <div data-testid="journal-day-empty" className="flex flex-1 flex-col items-center justify-center gap-2">
            <p className="text-body text-ink-muted">{t("journal.day.empty")}</p>
            <EmptyState id="journal" onAction={() => router.push("/today")} />
          </div>
        ) : null}

        {view.kind === "ready" && view.day.entries.length > 0 ? (
          <>
            <p className="text-caption text-ink-muted">
              {t("journal.day.count", { count: view.day.entries.length })}
            </p>
            <ul className="flex flex-col gap-3">
              {view.day.entries.map((entry) => (
                <EntryRow
                  key={entry.ref}
                  entry={entry}
                  onDelete={() => {
                    setDeleteError(null);
                    setPending(entry);
                  }}
                />
              ))}
            </ul>
          </>
        ) : null}
      </main>

      {pending ? (
        <ConfirmDeleteSheet
          scope="journal_entry"
          open
          onClose={() => setPending(null)}
          busy={busy}
          error={deleteError}
          onConfirm={async (choice) => {
            setBusy(true);
            const result = await deleteArtefact({
              artefactType: pending.artefact_type,
              artefactRef: pending.ref,
              deleteMemories: choice.deleteMemories,
              messageIds: sourceMessageIds(pending),
            });
            setBusy(false);
            if (!result.ok) {
              setDeleteError(result.error);
              return;
            }
            setPending(null);
            await refresh();
          }}
        />
      ) : null}
    </div>
  );
}
