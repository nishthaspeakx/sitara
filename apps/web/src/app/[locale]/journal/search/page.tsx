"use client";

/**
 * S23 Journal search — §29.1 `/journal/search`, §30.5's P0.
 *
 * ── What P0 search IS, stated because it is easy to over-promise ──────────
 *
 * §30.5: "P0 keyword+filters (type: brief/reflection/call/guidance/memory;
 * date; family member) over Journal+thread via Atlas Search; natural-language
 * search P1". So this screen offers keywords and type filters and orders by
 * DATE, newest first — the contract an exact scan satisfies exactly. The Atlas
 * index is a scale ceiling and is not built (community Mongo has no
 * `createSearchIndexes`, so an Atlas backend could not have run once before
 * shipping); it is filed as its own release gate. Nothing here implies
 * relevance ranking, because nothing here computes one.
 *
 * ── §30.5's sensitive-search rule is the server's, and only the server's ──
 *
 * "Searching health-adjacent or safety-flagged content shows results to the
 * user (her data) but never resurfaces L4 content as casual suggestions."
 * `GET /v1/journal/search` passes `SearchMode.EXPLICIT` and has no parameter
 * that could change it: this screen exists because a person typed something, so
 * her own L4 content is hers to find. The suggestion path is a different caller
 * with a different mode. There is deliberately nothing here that filters
 * results — a client-side filter would be a second implementation of a safety
 * rule, disagreeing with the first exactly where it matters.
 *
 * ── The filters are chips in a scroller, not a SegmentedControl ───────────
 *
 * §30.5's filter set is six wide once "everything" is counted, and six segments
 * across the 390-point design target (§24.5, never mind §29.3's 320) is a row
 * of truncated labels in every locale and an unreadable one in Devanagari,
 * which sets wider at the same nominal size. The chip's `filter` variant is
 * `role="switch"` and already carries its selected state without relying on
 * colour (§29.4), so nothing is lost by scrolling them.
 */

import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import type { ErrorEnvelope } from "@sitara/schemas";

import {
  Card,
  Chip,
  EmptyState,
  ErrorState,
  Header,
  SearchField,
  Skeleton,
} from "@/components/ui";
import { useRouter } from "@/i18n/navigation";
import { formatShortDate } from "@/lib/dates";
import { ARTEFACT_TYPES, searchJournal, type ArtefactType, type SearchHit } from "@/lib/journal";

type View =
  | { kind: "idle" }
  | { kind: "searching" }
  | { kind: "ready"; hits: SearchHit[] }
  | { kind: "error"; error: ErrorEnvelope };

/** §30.5 lists `memory` among the filters; the Vault is its own surface and its
 *  own endpoint, so the Journal's filter set is the four artefact types that
 *  live in the timeline plus `milestone`. A filter that queried a collection
 *  this endpoint does not read would return nothing and look like a bug. */
const FILTERS = ARTEFACT_TYPES;

export default function JournalSearchPage() {
  const t = useTranslations();
  const locale = useLocale();
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<ArtefactType | "all">("all");
  const [view, setView] = useState<View>({ kind: "idle" });
  // Every keystroke is a request otherwise, and the last one to come back wins
  // regardless of which one was typed last.
  const latest = useRef(0);

  const run = useCallback(
    async (text: string, filter: ArtefactType | "all") => {
      const token = (latest.current += 1);
      if (text.trim().length === 0) {
        setView({ kind: "idle" });
        return;
      }
      setView({ kind: "searching" });
      const result = await searchJournal(text.trim(), filter === "all" ? [] : [filter]);
      if (token !== latest.current) return;
      setView(result.ok ? { kind: "ready", hits: result.data } : { kind: "error", error: result.error });
    },
    [],
  );

  useEffect(() => {
    const timer = setTimeout(() => void run(query, filter), 200);
    return () => clearTimeout(timer);
  }, [query, filter, run]);

  return (
    <div data-testid="journal-search" className="flex min-h-app flex-col bg-bg-canvas">
      <Header variant="titled" titleKey="journal.search.title" onBack={() => router.back()} />

      <main className="flex flex-1 flex-col gap-4 px-5 pb-10 pt-4">
        <SearchField
          value={query}
          onChange={setQuery}
          labelKey="journal.search.title"
          placeholderKey="journal.search.placeholder"
        />

        {/* Chips, not a SegmentedControl — see the file header. */}
        <fieldset>
          <legend className="pb-2 text-caption text-ink-muted">
            {t("journal.search.filter_label")}
          </legend>
          <div className="-mx-5 flex gap-2 overflow-x-auto px-5 pb-1">
            <Chip
              variant="filter"
              selected={filter === "all"}
              onClick={() => setFilter("all")}
            >
              {t("journal.search.filter_all")}
            </Chip>
            {FILTERS.map((type) => (
              <Chip
                key={type}
                variant="filter"
                selected={filter === type}
                onClick={() => setFilter(type)}
              >
                {t(`journal.type.${type}`)}
              </Chip>
            ))}
          </div>
        </fieldset>

        {view.kind === "idle" ? (
          <p data-testid="search-prompt" className="text-body text-ink-muted">
            {t("journal.search.prompt")}
          </p>
        ) : null}

        {view.kind === "searching" ? <Skeleton variant="list" /> : null}

        {view.kind === "error" ? (
          <ErrorState error={view.error} onRetry={() => void run(query, filter)} />
        ) : null}

        {view.kind === "ready" ? (
          <>
            <p data-testid="search-count" className="text-caption text-ink-muted">
              {t("journal.search.results", { count: view.hits.length })}
            </p>
            {view.hits.length === 0 ? (
              <div className="flex flex-1 items-center justify-center">
                <EmptyState id="search_results" onAction={() => setQuery("")} />
              </div>
            ) : (
              <ul className="flex flex-col gap-3">
                {view.hits.map((hit) => {
                  // A BARE identifier — `i18n-lint` matches the literal
                  // template text and cannot expand `${hit.artefact_type}`.
                  const type = hit.artefact_type;
                  return (
                    <li key={hit.ref} data-testid="search-hit" data-ref={hit.ref}>
                      <Card
                        className="flex flex-col gap-2"
                        onClick={() => router.push(`/journal/${hit.local_date}`)}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <Chip>{t(`journal.type.${type}`)}</Chip>
                          <span className="text-caption text-ink-muted">
                            {formatShortDate(hit.local_date, locale)}
                          </span>
                        </div>
                        <p className="text-body text-ink-primary">{hit.preview}</p>
                      </Card>
                    </li>
                  );
                })}
              </ul>
            )}
          </>
        ) : null}
      </main>
    </div>
  );
}
