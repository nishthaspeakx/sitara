/**
 * §30.5's Memory Vault — "the 11 typed facts with consent stamps, never a
 * content archive".
 *
 * ── There is no GET by id, and that is the API's answer rather than a gap ───
 *
 * `memory/router.py` serves list, accept, edit, mute, delete and the two scoped
 * effects. It does NOT serve `/v1/memories/{id}`, so S26 finds its row in the
 * list. That is deliberate here rather than worked around: inventing a client
 * call to an endpoint the real API does not expose is the same defect as a fake
 * accepting what the real system rejects, pointed the other way — it would pass
 * every test against a stub written to match the client, and 404 in production.
 *
 * The cost is one list read for a detail view, on a collection §32.4 caps at
 * eleven types of thing a person has personally agreed to. The cost of the
 * alternative is a screen that cannot work.
 */

import { MEMORY_TYPES, type MemoryType } from "@sitara/schemas";

import { apiCall, type ApiResult } from "./api";

export { MEMORY_TYPES, type MemoryType };

/** §30.5: deleting a conversation marks dependent sources removed; the memory survives. */
export const SOURCE_STATES = ["present", "removed"] as const;
export type SourceState = (typeof SOURCE_STATES)[number];

export interface Memory {
  memory_id: string;
  type: MemoryType;
  content: string;
  consent_granted_at: string;
  wording_reconfirmed: boolean;
  muted: boolean;
  source_state: SourceState;
  decay_score: number;
  created_at: string | null;
}

/**
 * §30.5's vault list — decayed and muted rows included.
 *
 * It is the user's inventory of what Tara knows, not a retrieval ranking, so a
 * row Tara would not currently use is still a row she is entitled to see. A
 * vault that hid muted memories would be a vault that could not be audited,
 * which is the one thing it is for.
 */
export function loadVault(types: readonly MemoryType[] = []): Promise<ApiResult<Memory[]>> {
  const params = new URLSearchParams();
  // §30.5: "Vault filters use exactly these 11 labels" — the parameter is named
  // `type` because that is the label the client filters on.
  for (const type of types) params.append("type", type);
  const query = params.toString();
  return apiCall<Memory[]>(`/v1/memories${query ? `?${query}` : ""}`);
}

/**
 * §30.5's "don't remember this": withheld from retrieval, kept in the vault,
 * REVERSIBLE. Deletion is the other call and is not.
 *
 * The two live next to each other here on purpose. They are the pair a screen
 * must never present at the same weight, and the day someone reaches for the
 * wrong one is the day a person loses something she meant to set aside.
 */
export function setMuted(memoryId: string, muted: boolean): Promise<ApiResult<Memory>> {
  return apiCall<Memory>(`/v1/memories/${encodeURIComponent(memoryId)}/mute`, {
    method: "POST",
    body: JSON.stringify({ muted }),
  });
}

/**
 * Hard delete, embedding included (diagram 8).
 *
 * §44.5: the service additionally writes the withdrawal to the permanent §13
 * consent ledger — content-free, so a user who deletes a memory can still show
 * that she did. That is server-side and this call does not and must not carry
 * anything about it: a client-supplied ledger entry would be a client-supplied
 * legal record.
 */
export function forgetMemory(memoryId: string): Promise<ApiResult<null>> {
  return apiCall<null>(`/v1/memories/${encodeURIComponent(memoryId)}`, { method: "DELETE" });
}

/** The one place a detail view resolves its row. See the header for why. */
export function findMemory(memories: readonly Memory[], memoryId: string): Memory | undefined {
  return memories.find((memory) => memory.memory_id === memoryId);
}
