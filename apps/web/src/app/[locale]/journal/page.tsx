"use client";

/**
 * S21 Journal — §29.1 `/journal`, §30.5's calendar+list.
 *
 * §30.5's rule in one sentence: **Journal is what happened.** Not what Tara
 * knows (that is the Vault, `/you/memories`) and not where talk lives (that is
 * the thread). So this surface merges four artefact types that live in four
 * different collections and stores none of them — the API assembles the day and
 * every `preview` is rendered from wherever the artefact actually is.
 *
 * A day with nothing in it does not appear here; a day with an artefact whose
 * SOURCE is gone does, with the row saying so (`EntryRow`). The distinction
 * matters: the first is a quiet Tuesday, the second is a broken link, and
 * collapsing them would hide the second forever.
 *
 * The year view §30.5 calls "the life timeline" is P1 polish and is not here.
 */

import { Search } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import type { ErrorEnvelope } from "@sitara/schemas";

import { ConfirmDeleteSheet } from "@/components/deletion/ConfirmDeleteSheet";
import { EntryRow } from "@/components/journal/EntryRow";
import {
  EmptyState,
  ErrorState,
  Header,
  IconButton,
  Skeleton,
  TabBar,
} from "@/components/ui";
import { ICON_STROKE } from "@/components/ui/_util";
import { useRouter } from "@/i18n/navigation";
import { formatLongDate } from "@/lib/dates";
import {
  deleteArtefact,
  loadTimeline,
  sourceMessageIds,
  type JournalDay,
  type JournalEntry,
} from "@/lib/journal";
import { useLocale } from "next-intl";

type View =
  | { kind: "loading" }
  | { kind: "ready"; days: JournalDay[] }
  | { kind: "error"; error: ErrorEnvelope };

export default function JournalPage() {
  const locale = useLocale();
  const router = useRouter();
  const [view, setView] = useState<View>({ kind: "loading" });
  const [pending, setPending] = useState<JournalEntry | null>(null);
  const [busy, setBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<ErrorEnvelope | null>(null);

  const refresh = useCallback(async () => {
    const result = await loadTimeline();
    setView(result.ok ? { kind: "ready", days: result.data } : { kind: "error", error: result.error });
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <div data-testid="journal" className="flex min-h-screen flex-col bg-bg-canvas">
      <Header
        variant="titled"
        titleKey="journal.title"
        subtitleKey="journal.subtitle"
        actions={
          <IconButton
            variant="plain"
            labelKey="journal.open_search"
            data-testid="journal-search-link"
            onClick={() => router.push("/journal/search")}
            icon={<Search strokeWidth={ICON_STROKE} />}
          />
        }
      />

      <main className="flex flex-1 flex-col gap-4 px-5 pb-10 pt-4">
        {view.kind === "loading" ? <Skeleton variant="list" /> : null}

        {view.kind === "error" ? (
          <ErrorState error={view.error} onRetry={() => void refresh()} />
        ) : null}

        {view.kind === "ready" && view.days.length === 0 ? (
          // §24.6's designed empty state, with its own action — never a blank
          // screen and never a dead end.
          <div className="flex flex-1 items-center justify-center">
            <EmptyState id="journal" onAction={() => router.push("/today")} />
          </div>
        ) : null}

        {view.kind === "ready"
          ? view.days.map((day) => (
              <section key={day.local_date} data-testid="journal-day-group" data-date={day.local_date}>
                {/* The heading is the DATE, formatted in-locale including its
                    numerals (§2.4) — never an ISO string, which is a machine's
                    idea of a day. */}
                <h2 className="pb-2 font-serif text-h3 text-ink-primary">
                  <button
                    type="button"
                    data-testid="open-day"
                    onClick={() => router.push(`/journal/${day.local_date}`)}
                    className="text-start underline decoration-gold underline-offset-4"
                  >
                    {formatLongDate(day.local_date, locale)}
                  </button>
                </h2>
                <ul className="flex flex-col gap-3">
                  {day.entries.map((entry) => (
                    <EntryRow
                      key={entry.ref}
                      entry={entry}
                      onOpen={() => router.push(`/journal/${entry.local_date}`)}
                      onDelete={() => {
                        setDeleteError(null);
                        setPending(entry);
                      }}
                    />
                  ))}
                </ul>
              </section>
            ))
          : null}
      </main>

      <TabBar active="journal" onSelect={(tab) => router.push(`/${tab}`)} />

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
              // What she ticked, and nothing this screen decided for her.
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
