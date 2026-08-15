/**
 * §32.15's family records, and §45's alternative to destroying one.
 *
 * Two shapes here are load-bearing rather than stylistic, and both are the
 * API's shapes for the same reasons:
 *
 * **The deletion takes memory IDS, not a boolean.** §32.15 says the checkbox is
 * offered with the candidates "listed", so the screen shows what would go and
 * sends back what she ticked. A boolean would move the judgement about which
 * memories are "about them" from the user to a name match.
 *
 * **`memoriesAbout` is a separate call from the deletion.** The list has to be
 * seen before it can be consented to, and one call that both listed and deleted
 * would make the confirm step optional.
 */

import { apiCall, type ApiResult } from "./api";

/** §32.15's closed relation set — a label in three locales, never free text. */
export const RELATIONS = [
  "partner",
  "mother",
  "father",
  "daughter",
  "son",
  "sister",
  "brother",
  "grandmother",
  "grandfather",
  "friend",
  "other",
] as const;
export type Relation = (typeof RELATIONS)[number];

/**
 * §45 (CC-012). Two states, and `living` is the default everywhere.
 *
 * An enum rather than a `remember: true` flag, because §45.2 makes the
 * conversion reversible and a one-way verb would quietly say otherwise.
 */
export const MEMORIAL_STATES = ["living", "in_memory"] as const;
export type MemorialState = (typeof MEMORIAL_STATES)[number];

export interface FamilyMember {
  member_id: string;
  relation: Relation;
  name: string;
  language_tag: string;
  has_birth_details: boolean;
  /** §13's gate. The TIMESTAMP is evidence and stays server-side. */
  attested: boolean;
  memorial_state: MemorialState;
  created_at: string | null;
}

/** One candidate for §32.15's checkbox, with the content she is deciding about. */
export interface MemoryAboutMember {
  memory_id: string;
  type: string;
  content: string;
}

/** What the deletion DID, so the screen can say so afterwards. */
export interface DeletionEffects {
  birth_details: number;
  charts: number;
  memories: number;
  member_removed: boolean;
  attestation_retained: boolean;
}

export function loadMembers(): Promise<ApiResult<FamilyMember[]>> {
  return apiCall<FamilyMember[]>("/v1/family");
}

export function loadMember(memberId: string): Promise<ApiResult<FamilyMember>> {
  return apiCall<FamilyMember>(`/v1/family/${encodeURIComponent(memberId)}`);
}

/**
 * §32.15's "listed", read BEFORE the sheet renders its checkboxes.
 *
 * `memories` has no family-member field in §6.4, so "about them" is a NAME
 * MATCH and nothing more. That is a judgement, and it is shown to the user
 * precisely because it is one: performed silently it would take "Sudha's
 * birthday is 11 March" along with a stranger's remark containing the word.
 */
export function loadMemoriesAbout(memberId: string): Promise<ApiResult<MemoryAboutMember[]>> {
  return apiCall<MemoryAboutMember[]>(`/v1/family/${encodeURIComponent(memberId)}/memories`);
}

/**
 * §45's conversion, both directions.
 *
 * Its own call rather than a field on the deletion, and that is not tidiness:
 * they are opposite acts. One destroys birth details, charts and — if she ticks
 * them — memories; this one writes a single field and touches nothing else.
 * Sharing a request body would put them one boolean apart.
 */
export function setMemorialState(
  memberId: string,
  state: MemorialState,
): Promise<ApiResult<FamilyMember>> {
  return apiCall<FamilyMember>(`/v1/family/${encodeURIComponent(memberId)}/memorial`, {
    method: "POST",
    body: JSON.stringify({ memorial_state: state }),
  });
}

/**
 * §32.15's deletion.
 *
 * `deleteMemoryIds` empty IS the default-keep promise. There is deliberately no
 * "delete all memories about them" convenience: §32.15 says listed, and a flag
 * is the opposite of listed.
 */
export function deleteMember(
  memberId: string,
  deleteMemoryIds: readonly string[],
): Promise<ApiResult<DeletionEffects>> {
  return apiCall<DeletionEffects>(`/v1/family/${encodeURIComponent(memberId)}/delete`, {
    method: "POST",
    body: JSON.stringify({ delete_memory_ids: [...deleteMemoryIds] }),
  });
}
