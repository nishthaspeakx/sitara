/**
 * §27's night reflection (S24), through the one API door.
 *
 * **The date is a parameter, never a server-side "today".** §27 binds a
 * reflection to the user's local calendar day at creation, and only the client
 * knows which day that is for her — a server substituting its own would move a
 * traveller's reflection to a day she was not there for. The route is
 * `/v1/reflection/{local_date}` for exactly that reason.
 *
 * The day comes from the Today payload's `local_time`/date, not from
 * `new Date()`. `today/sky.ts` records why: a screen that read the browser
 * clock would render a different day than the brief it took over from, and
 * every baseline would depend on when CI ran.
 */

import { apiCall, type ApiResult } from "./api";

/** §10-17's three prompts, as IDs. The wording lives in the catalogs (§2.4). */
export const PROMPTS = ["gratitude", "weight", "tomorrow"] as const;
export type Prompt = (typeof PROMPTS)[number];

/**
 * §27's five plain states, and deliberately no numeric scale: §0.8 asks for
 * closure, and a 1–10 slider on a bad night is a test she can fail.
 */
export const MOODS = ["heavy", "tired", "steady", "light", "joyful"] as const;
export type Mood = (typeof MOODS)[number];

export interface ReflectionEntry {
  prompt: Prompt;
  text: string;
}

export interface Reflection {
  date: string;
  locale: string;
  entries: ReflectionEntry[];
  mood: Mood | null;
  memory_chips: string[];
  /**
   * The ceremony's order, SERVED rather than assumed from `PROMPTS`.
   *
   * `PROMPTS` above is the closed set — what a valid id is. This is the order
   * to ask them in, and it is the server's answer for the same reason §34.3's
   * module enum is: two declarations of an order are two things that can
   * disagree, and here they would disagree about the shape of a ceremony.
   */
  prompt_order: Prompt[];
  started: boolean;
}

export function loadReflection(localDate: string, locale: string): Promise<ApiResult<Reflection>> {
  const params = new URLSearchParams({ locale });
  return apiCall<Reflection>(
    `/v1/reflection/${encodeURIComponent(localDate)}?${params.toString()}`,
  );
}

export interface SaveReflection {
  locale: string;
  entries: Partial<Record<Prompt, string>>;
  mood?: Mood | null;
  memoryChips?: string[];
}

/**
 * A PUT because it is idempotent on (user, date). §6.4's unique index means a
 * second send updates rather than duplicates — which is what makes it safe to
 * save as she writes rather than only at the end, and §29.2 wants no moment
 * where closing the app loses the evening.
 */
export function saveReflection(
  localDate: string,
  input: SaveReflection,
): Promise<ApiResult<Reflection>> {
  return apiCall<Reflection>(`/v1/reflection/${encodeURIComponent(localDate)}`, {
    method: "PUT",
    body: JSON.stringify({
      locale: input.locale,
      entries: input.entries,
      mood: input.mood ?? null,
      memory_chips: input.memoryChips ?? [],
    }),
  });
}
