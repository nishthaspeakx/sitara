"use client";

/**
 * §28.2's FIRST-SESSION variant, which is also its empty state.
 *
 * "empty (pre-first-brief) = first-session variant" — so the one thing this
 * must not be is a generic `EmptyState`. §28.2 gives the morning-before-the-
 * first-morning three specific things, and the middle one is a promise:
 *
 *   "first-reading recap card + 'your first morning brief arrives at 7:00'
 *    promise + brief-time edit"
 *
 * The promise names the user's OWN brief time, not the 07:00 default §28.2
 * happens to use as its example. A user who chose 05:30 at S12 and is told
 * their brief arrives at 7:00 has been given a small, checkable falsehood on
 * the first screen after onboarding — which is an expensive place to spend
 * trust §0.17 has just finished earning.
 */

import { useTranslations } from "next-intl";

import type { TodayPayload } from "@sitara/schemas";

import { Button, Card } from "@/components/ui";
import { Link } from "@/i18n/navigation";

export function FirstSession({
  payload,
  onEditBriefTime,
}: {
  payload: TodayPayload;
  onEditBriefTime?: () => void;
}) {
  const t = useTranslations();

  return (
    <div className="flex flex-col gap-4">
      <Card measure data-testid="first-session-recap">
        <div data-testid="first-session-recap" className="flex flex-col gap-2">
          <h2 className="font-serif text-h3 text-ink-primary">{t("today.recap.title")}</h2>
          <p className="text-body text-ink-primary">{t("today.recap.body")}</p>
          <Link
            href="/start/reading"
            className="self-start rounded-chip px-2 py-1 text-caption text-ink-primary underline decoration-gold underline-offset-4"
          >
            {t("today.recap.action")}
          </Link>
        </div>
      </Card>

      <p data-testid="brief-promise" className="text-body text-ink-primary">
        {t("today.promise", { time: payload.state.brief_time })}
      </p>

      <Button
        variant="secondary"
        data-testid="brief-time-edit"
        onClick={onEditBriefTime}
        className="self-start"
      >
        {t("today.brief_time.edit")}
      </Button>

      <p className="text-caption text-ink-muted">{t("today.how_it_works")}</p>
    </div>
  );
}
