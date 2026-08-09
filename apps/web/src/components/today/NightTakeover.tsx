"use client";

/**
 * §28.2 item (7): "night: the whole tab transforms after 20:00 (dusk tokens,
 * reflection CTA replaces core card position)".
 *
 * "Replaces the core card POSITION" is the part that matters structurally: the
 * reflection prompt does not sit beside the core card, it stands where the core
 * card stood. That is why `TodayScreen` renders this INSTEAD of the core card
 * rather than in addition to it — the one-dominant-card rule then holds at
 * night by construction, with no second thing to be dominant.
 *
 * §28.2 also says the morning brief is "archived to Journal" at night, so this
 * says where it went. A brief that simply disappeared at 20:00 would read as a
 * bug to anyone who opened the app late.
 */

import { useTranslations } from "next-intl";
import { useState } from "react";

import type { TodayPayload } from "@sitara/schemas";

import { ReflectionPrompt } from "@/components/ui";

export function NightTakeover({
  payload,
  onSubmit,
}: {
  payload: TodayPayload;
  onSubmit?: (text: string) => void;
}) {
  const t = useTranslations();
  const [value, setValue] = useState("");

  return (
    <section data-testid="night-takeover" className="flex flex-col gap-4">
      <h2 className="font-serif text-h2 text-ink-primary">{t("today.night.title")}</h2>
      <ReflectionPrompt
        prompt={t("today.night.prompt")}
        value={value}
        onChange={setValue}
        onSubmit={() => onSubmit?.(value)}
      />
      {payload.modules.length ? (
        <p className="text-caption text-ink-muted">{t("today.night.archived")}</p>
      ) : null}
    </section>
  );
}
