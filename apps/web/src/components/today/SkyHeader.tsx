"use client";

/**
 * §28.2 item (1): "date + tithi line, sky gradient matching local time, story
 * ring (P1 flag) on Tara's photo left, settings-bell right".
 *
 * Not the §24.3 `Header`. That component's three variants carry a title from a
 * message KEY and a subtitle from a message key, and both of Today's header
 * lines are DATA — a formatted local date and a tithi rendered from a fact.
 * Bending `Header` to take two data strings and a gradient would make a
 * screen-specific header out of a shared one; composing the library's pieces
 * here leaves `Header` alone.
 *
 * The date is formatted by `next-intl`, so it is the locale's own calendar
 * conventions rather than a hand-built string — §2.4's rule reaches numerals
 * and dates, not only words.
 */

import { Bell } from "lucide-react";
import { useFormatter } from "next-intl";

import type { TodayPayload } from "@sitara/schemas";

import { IconButton, StoryRing } from "@/components/ui";
import type { TodayChrome } from "@/lib/today-variant";

import { skyFor } from "./sky";

export interface SkyHeaderProps {
  payload: TodayPayload;
  chrome: TodayChrome;
  onOpenSettings?: () => void;
  onOpenStories?: () => void;
}

export function SkyHeader({ payload, chrome, onOpenSettings, onOpenStories }: SkyHeaderProps) {
  const format = useFormatter();
  const sky = skyFor(chrome.band);

  // The tithi line, from the panchang the brief already carries. Absent on a
  // morning whose panchang never arrived — §28.2 gives the header a date line
  // regardless, and an empty "·" would be worse than one line.
  const tithi = payload.panchang.find((entry) => entry.label_key === "ui.panchang.tithi");

  return (
    <header
      data-testid="today-sky-header"
      className="relative flex flex-col pt-safe"
    >
      {/* The gradient carries NO text — see `sky.ts` for the six contrast
          failures that established the rule. */}
      <div aria-hidden="true" className={`${sky.strip} ${sky.height} w-full`} />

      <div className="-mt-6 flex items-center gap-3 px-5 pb-2">
        {/* §30.6: `enabled` defaults to false, so a P0 build hides the ring
            even if this screen forgot the flag. It is passed explicitly
            anyway — the default is a safety net, not the decision. */}
        <StoryRing
          enabled={payload.state.story_ring_enabled}
          taraState={chrome.night ? "night" : "profile_portrait"}
          onOpen={onOpenStories}
        />

        <div className="flex min-w-0 flex-1 flex-col">
          <h1 className="truncate font-serif text-h3 text-ink-primary">
            {format.dateTime(new Date(payload.local_date), {
              weekday: "long",
              day: "numeric",
              month: "long",
            })}
          </h1>
          {tithi ? (
            <p data-testid="tithi-line" className="truncate text-caption text-ink-muted">
              {tithi.value}
            </p>
          ) : null}
        </div>

        <IconButton
          icon={<Bell />}
          labelKey="today.aria.settings"
          onClick={onOpenSettings}
          className="shrink-0"
        />
      </div>
    </header>
  );
}
