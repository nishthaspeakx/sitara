"use client";

/**
 * §28.2 item (4): "colour · number · one favourable window · one caution
 * window (compact chips, ONE ROW)".
 *
 * One row is a rule, not a layout preference — the strip's job is to be
 * glanceable past on the way to the core card, and a strip that wraps to three
 * rows on a Devanagari or Hinglish build has stopped being a strip. So it
 * scrolls horizontally rather than wrapping, and `today-screens.spec.ts`
 * captures it in all three locales.
 *
 * Each chip carries its module's own confidence. §5.4's state is a property of
 * the evidence, and the four here genuinely differ: a colour derived from the
 * tithi and a window from a muhurat are not equally sure.
 */

import { useTranslations } from "next-intl";

import type { TodayModule } from "@sitara/schemas";

import { ConfidenceChip } from "@/components/ui";

export function PracticalStrip({ modules }: { modules: TodayModule[] }) {
  const t = useTranslations();
  return (
    <section
      data-testid="practical-strip"
      aria-label={t("today.practical")}
      // overflow-x rather than flex-wrap: §28.2 says one row, and a longer
      // locale must scroll, not restack.
      className="-mx-5 flex snap-x gap-2 overflow-x-auto px-5 pb-1"
    >
      {/* Destructured so the i18n key reads `ui.module.${module}` — the exact
          template declared in `dynamic-keys.json`. The lint matches the literal
          text of the template, and it is right to: a key assembled from
          `${card.module}` is a key it cannot expand and therefore cannot
          verify, which is how a missing translation reaches a user as a raw
          dotted key. */}
      {modules.map(({ module, text, confidence }) => (
        <div
          key={module}
          data-module={module}
          // A FIXED width, not `min-w`. Sized to its content, the colour
          // chip's sentence is wider than a 390px viewport, so it filled the
          // row and pushed the other three off-screen — one row, one chip,
          // which is not what §28.2 means by a strip. A fixed width makes the
          // next chip peek, which is what tells a reader the row scrolls.
          className="flex w-52 shrink-0 snap-start flex-col gap-1 rounded-card border border-border-subtle bg-surface px-3 py-2"
        >
          <span className="text-caption text-ink-muted">{t(`ui.module.${module}`)}</span>
          <span className="text-body text-ink-primary">{text}</span>
          <ConfidenceChip state={confidence} />
        </div>
      ))}
    </section>
  );
}
