/**
 * §30.5's Journal, through the one API door.
 *
 * **The Journal is a VIEW, and this module never forgets it.** §30.5's rule is
 * "Journal is what happened; the Vault is what Tara knows; the thread is where
 * talk lives", and the API follows it: a day is assembled from artefacts that
 * live in `daily_briefings`, `night_reflections`, `call_sessions.summary` and
 * CC-011's save pointers. `preview` is rendered from wherever the artefact
 * actually is, which is why it can be `null` — the source is gone and the row
 * says so, rather than being dropped as if the day had not happened.
 *
 * Nothing here caches. Today caches because §28.2 designs an offline variant
 * around a brief that was true when it was taken; a journal read has no such
 * variant, and a stale timeline that silently omitted this morning would be
 * worse than an honest error.
 */

import { apiCall, type ApiResult } from "./api";

/**
 * §30.5's five artefact types, as `journal/models.py` declares them.
 *
 * The first four can be SAVED (§44.2); `milestone` is derived from dates the
 * system already holds and has nothing to point at, which is why
 * `journal_saves` never carries one.
 */
export const ARTEFACT_TYPES = ["brief", "reflection", "call", "guidance", "milestone"] as const;
export type ArtefactType = (typeof ARTEFACT_TYPES)[number];

export interface JournalEntry {
  artefact_type: ArtefactType;
  /** `type:id` — opaque here, and the only handle a deletion needs. */
  ref: string;
  local_date: string;
  saved: boolean;
  save_id: string | null;
  note: string | null;
  /**
   * Rendered from where the artefact lives — the Journal keeps no copy
   * (§44.2). `null` where the source is gone; the row is still shown.
   */
  preview: string | null;
  message_id: string | null;
  conversation_id: string | null;
  confidence: string | null;
  occurred_at: string | null;
}

export interface JournalDay {
  local_date: string;
  entries: JournalEntry[];
}

export interface SearchHit {
  artefact_type: ArtefactType;
  ref: string;
  local_date: string;
  preview: string;
  message_id: string | null;
  conversation_id: string | null;
}

export function loadTimeline(): Promise<ApiResult<JournalDay[]>> {
  return apiCall<JournalDay[]>("/v1/journal");
}

export function loadDay(localDate: string): Promise<ApiResult<JournalDay>> {
  // Encoded even though a date has no unsafe characters: the value reaches
  // here from a route segment, and a route segment is user input.
  return apiCall<JournalDay>(`/v1/journal/${encodeURIComponent(localDate)}`);
}

/**
 * §30.5's P0 search: keyword + filters, newest first.
 *
 * Deliberately not a relevance score. That contract is the one an exact scan
 * satisfies EXACTLY, and §30.5's Atlas Search half is not built — community
 * Mongo has no `createSearchIndexes`, so an Atlas backend could not have run
 * once before shipping. What is deferred is the index, a scale ceiling; the
 * contract is met.
 */
export function searchJournal(
  query: string,
  types: readonly ArtefactType[] = [],
): Promise<ApiResult<SearchHit[]>> {
  const params = new URLSearchParams({ q: query });
  for (const type of types) params.append("type", type);
  return apiCall<SearchHit[]>(`/v1/journal/search?${params.toString()}`);
}

export interface DeleteArtefact {
  artefactType: ArtefactType;
  artefactRef: string;
  /**
   * §30.5's checkbox. **The caller passes what the user ticked and nothing
   * else** — there is no default here, because a default would be this module
   * making a promise the confirm sheet is supposed to make.
   */
  deleteMemories: boolean;
  /**
   * The turns the artefact was built from, which is how a memory is known to
   * be sourced from it. Derived by the caller from the entry's `message_id`:
   * the API serves one pointer per entry, so the list a screen sends is a list
   * it can account for. An empty list means the checkbox has nothing to act on
   * and it is not offered.
   */
  messageIds: string[];
}

export interface DeleteEffects {
  deleted: number;
  memories_deleted: number;
}

/**
 * A POST rather than a DELETE, mirroring the API — it carries a body, and a
 * DELETE with a body is a thing intermediaries are entitled to drop. Losing it
 * here would silently flip the checkbox to its default: the safe direction, but
 * by accident rather than by decision.
 */
export function deleteArtefact(input: DeleteArtefact): Promise<ApiResult<DeleteEffects>> {
  return apiCall<DeleteEffects>("/v1/journal/delete", {
    method: "POST",
    body: JSON.stringify({
      artefact_type: input.artefactType,
      artefact_ref: input.artefactRef,
      delete_memories: input.deleteMemories,
      message_ids: input.messageIds,
    }),
  });
}

/**
 * The source turns an entry's deletion would reach.
 *
 * One place, so no screen invents its own idea of what "sourced from this" is.
 * §30.5's checkbox is offered only where this is non-empty — a checkbox over an
 * empty list is a control that promises an effect it cannot have.
 */
export function sourceMessageIds(entry: JournalEntry): string[] {
  return entry.message_id ? [entry.message_id] : [];
}
