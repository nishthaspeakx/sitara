"use client";

/**
 * S12's voice preview — Tara says the user's name (§29.1, §0.11 item 11).
 *
 * A dedicated client rather than `apiCall`, for one reason: `apiCall` parses
 * every response as JSON, and this endpoint answers with `audio/wav`. Making it
 * tolerate a blob would put a branch in the app's one API door for a single
 * caller, and the branch would be reached by every other call forever.
 *
 * **There is no `text` parameter here either.** The route takes none — the
 * sentence is a catalog key resolved server-side in the account's locale (see
 * `services/api/src/sitara_api/voice/preview.py`). This module could not send
 * one if it wanted to, which is the point: the guarantee is only worth having
 * if it holds at every layer that could have broken it.
 */

import type { ErrorEnvelope } from "@sitara/schemas";

import { apiUrl } from "./api";

export type PreviewResult =
  | { ok: true; url: string }
  | { ok: false; error: ErrorEnvelope };

const TRANSPORT_FAILURE: ErrorEnvelope = {
  code: "SYS_UNAVAILABLE",
  message_key: "errors.sys.unavailable",
  trace_id: "transport",
  retryable: true,
} as ErrorEnvelope;

/**
 * Fetch the preview and return an object URL the caller can play.
 *
 * The caller OWNS the returned url and must `revokeVoicePreview` it — a blob
 * URL pins its bytes in memory until revoked, and this screen can be replayed
 * as many times as someone likes.
 */
export async function fetchVoicePreview(): Promise<PreviewResult> {
  try {
    const response = await fetch(apiUrl("/v1/voice/preview"), {
      method: "POST",
      // §34.5: httpOnly, first-party. Same posture as every other call.
      credentials: "same-origin",
    });
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      if (body && typeof body === "object" && "message_key" in body) {
        return { ok: false, error: body as ErrorEnvelope };
      }
      return { ok: false, error: TRANSPORT_FAILURE };
    }
    return { ok: true, url: URL.createObjectURL(await response.blob()) };
  } catch {
    return { ok: false, error: TRANSPORT_FAILURE };
  }
}

export function revokeVoicePreview(url: string | null): void {
  if (url) URL.revokeObjectURL(url);
}

/**
 * §2.4-6's per-user name override — "that's not how it sounds".
 *
 * `null` clears it and returns Tara to saying the name as written. §3.4 keeps
 * this away from every surface that is READ rather than heard; the server
 * writes it beside `display_name` rather than over it.
 */
export async function saveNamePronunciation(
  spokenAs: string | null,
): Promise<boolean> {
  try {
    const response = await fetch(apiUrl("/v1/voice/settings/name-pronunciation"), {
      method: "PUT",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ override: spokenAs }),
    });
    return response.ok;
  } catch {
    return false;
  }
}
