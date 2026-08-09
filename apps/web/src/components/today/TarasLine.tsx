"use client";

/**
 * §28.2 item (2): "Tara's line — one warm sentence for this moment (the
 * emotional anchor, always present)".
 *
 * "Always present" is the whole contract, and it is why this renders on a
 * morning with no brief at all. The API composes the sentence in one of two
 * registers — cited when it leans on the day, claimless when there are no
 * facts — so there is never a version of this screen where the anchor is
 * missing because the panchang was late.
 *
 * It is deliberately NOT a card. It sits above the core card in the anatomy and
 * carries no chrome, because a card would make it compete with the one thing
 * §28.2 says nothing may compete with.
 */

import type { TodayPayload } from "@sitara/schemas";

import type { TodayChrome } from "@/lib/today-variant";

export function TarasLine({
  payload,
  chrome,
}: {
  payload: TodayPayload;
  chrome: TodayChrome;
}) {
  if (!payload.taras_line) return null;
  return (
    <p
      data-testid="taras-line"
      className={
        chrome.night
          ? "font-serif text-h3 text-ink-primary"
          : "font-serif text-h3 text-ink-primary"
      }
    >
      {payload.taras_line.text}
    </p>
  );
}
