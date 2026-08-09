/**
 * Story scaffolding for the §24.3 library.
 *
 * Every component ships an `AllStates` story: one panel holding every state the
 * spec names for it. That panel is what the Playwright suite screenshots, so a
 * baseline per component per locale covers all of that component's states in
 * one image and a regression in any state shows up as a diff.
 */

import * as React from "react";

export function StatePanel({ children }: { children: React.ReactNode }) {
  return <div className="flex flex-col gap-6">{children}</div>;
}

export function StateGroup({
  name,
  children,
  row = false,
}: {
  name: string;
  children: React.ReactNode;
  row?: boolean;
}) {
  return (
    <section className="flex flex-col gap-2">
      {/* a story label, not product copy — deliberately not an i18n key */}
      <h3 className="text-caption text-ink-muted">{name}</h3>
      <div className={row ? "flex flex-wrap items-center gap-3" : "flex flex-col gap-3"}>
        {children}
      </div>
    </section>
  );
}

/** Fixed sample values so screenshots stay byte-stable across runs. */
export const SAMPLE = {
  factLine:
    "The Moon moves through your tenth house today, so work themes rise before noon.",
  plainLanguage:
    "Today the Moon moves through your 10th house — work themes rise. Your birth time is exact, so this is precise.",
  detailLines: [
    "Moon in Purva Bhadrapada until 14:20",
    "Shukla Paksha, Dashami",
    "Sunrise 06:12 · Sunset 18:44",
  ],
  memory: "You are preparing for your sister's wedding in November.",
  transcript: "Tara, what should I keep in mind before the meeting tomorrow?",
  date: "12 March 2026",
  time: "07:00",
  city: "Bengaluru",
  name: "Meera",
  relation: "Sister",
  traceId: "7f3a91c4",
} as const;
