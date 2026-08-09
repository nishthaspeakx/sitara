/**
 * Today's data, through the one API door.
 *
 * `apiCall` already owns the origin, the credentials mode and the §34.4
 * envelope, so this module holds only what is specific to §28.2: the cache that
 * makes the offline variant possible, and the fact that a failed fetch is a
 * SCREEN rather than an error.
 *
 * ── The offline cache ──────────────────────────────────────────────────────
 *
 * §28.2's offline variant is "cached brief + offline banner; practical strip
 * marked 'as of [time]'", which only exists if something kept the last good
 * payload. That is here rather than in a service worker because the variant
 * needs the TIME the payload was taken, and "as of" is a promise about data
 * age that should be made by whatever stored it.
 */

import type { TodayPayload } from "@sitara/schemas";

import { apiCall, type ApiResult } from "./api";

const CACHE_KEY = "sitara.today.v1";

export interface CachedToday {
  payload: TodayPayload;
  /** Local "HH:MM" when it was stored — §28.2's "as of [time]". */
  cachedAt: string;
}

export async function fetchToday(): Promise<ApiResult<TodayPayload>> {
  const result = await apiCall<TodayPayload>("/v1/today");
  if (result.ok) cacheToday(result.data);
  return result;
}

export function cacheToday(payload: TodayPayload): void {
  if (typeof window === "undefined") return;
  try {
    const entry: CachedToday = {
      payload,
      // The user's own clock, formatted plainly. A cache stamped in UTC would
      // tell a Bengaluru user their brief is "as of 03:00".
      cachedAt: new Date().toTimeString().slice(0, 5),
    };
    window.localStorage.setItem(CACHE_KEY, JSON.stringify(entry));
  } catch {
    // A full or disabled store costs the offline variant, nothing else.
  }
}

export function readCachedToday(): CachedToday | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const entry = JSON.parse(raw) as CachedToday;
    return entry?.payload ? entry : null;
  } catch {
    return null;
  }
}
