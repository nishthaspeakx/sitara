"use client";

/**
 * §28.2 item (6): "panchang summary row → /today/timings".
 *
 * Renders nothing when the panchang did not arrive. `PanchangStrip` has an
 * `unavailable` state and it is the right one for a cell that was cold, but on
 * Today a missing panchang is already explained by the degraded note above —
 * saying it twice on one screen turns an honest limit into a complaint.
 */

import { useTranslations } from "next-intl";

import type { TodayModule, TodayPayload } from "@sitara/schemas";

import { BriefCard, PanchangStrip } from "@/components/ui";
import { Link } from "@/i18n/navigation";

export function PanchangRow({
  payload,
  row,
  onWhyThis,
}: {
  payload: TodayPayload;
  /**
   * `moon_nakshatra_note` — the ranking engine's PANCHANG_ROW bucket.
   *
   * It belongs here rather than among the contextual cards, and the difference
   * is not cosmetic: §28.2's densities describe it as "the panchang row"
   * (collapsed at LOW, present from MED), so listing it as a contextual card
   * would spend one of the max-four slots on something the density rules have
   * already accounted for — and show the day's nakshatra twice, once as a
   * sentence and once as a strip value.
   */
  row?: TodayModule;
  onWhyThis?: () => void;
}) {
  const t = useTranslations();
  if (payload.panchang.length === 0 && !row) return null;

  return (
    <section data-testid="panchang-row" className="flex flex-col gap-2">
      {row ? (
        <div data-module={row.module}>
          <BriefCard
            module={row.module}
            factLine={row.text}
            confidence={row.confidence}
            onWhyThis={onWhyThis}
          />
        </div>
      ) : null}
      {payload.panchang.length ? (
        <>
          <p className="text-caption text-ink-muted">{t("today.panchang.title")}</p>
          <PanchangStrip
            entries={payload.panchang.map((entry) => ({
              labelKey: entry.label_key,
              value: entry.value,
            }))}
          />
          {/* §28.2 item (6): "panchang summary row → /today/timings". S16 now
              exists, so the row leads somewhere — this link pointed at a 404
              for exactly as long as it did not, and its RSC prefetch hung every
              `networkidle` wait in the suite while it did. */}
          <Link
            href="/today/timings"
            data-testid="panchang-link"
            className="self-start rounded-chip px-2 py-1 text-caption text-ink-primary underline decoration-gold underline-offset-4"
          >
            {t("today.panchang.link")}
          </Link>
        </>
      ) : null}
    </section>
  );
}
