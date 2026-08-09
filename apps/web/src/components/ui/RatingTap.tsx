"use client";

/**
 * RatingTap — §24.3 feedback / §30.4 the feedback fabric.
 *
 * One tap, everywhere guidance appears: 👍 helpful · "not relevant" · **"this
 * looks wrong"**. The third one is the important one — §30.4 routes it into
 * structured triage (calculation / wrong person / wrong language / pronunciation)
 * and the ranking engine downweights on "not relevant".
 *
 * Once answered the control becomes an acknowledgement, not a scoreboard: no
 * counts, no streaks, nothing that turns feedback into a game.
 */

import { ThumbsUp, CircleSlash, Flag } from "lucide-react";
import { useTranslations } from "next-intl";

import { ICON_STROKE, cn, focusRing, motionStandard, touchTarget } from "./_util";

export type RatingChoice = "helpful" | "not_relevant" | "looks_wrong";

export interface RatingTapProps {
  /** The choice already made, if any. */
  value?: RatingChoice | null;
  onRate: (choice: RatingChoice) => void;
  className?: string;
}

const CHOICES: Array<{
  id: RatingChoice;
  Icon: React.ComponentType<{ strokeWidth?: number; className?: string }>;
}> = [
  { id: "helpful", Icon: ThumbsUp },
  { id: "not_relevant", Icon: CircleSlash },
  { id: "looks_wrong", Icon: Flag },
];

export function RatingTap({ value, onRate, className }: RatingTapProps) {
  const t = useTranslations();

  if (value) {
    return (
      <p className={cn("text-caption text-ink-muted", className)} role="status">
        {t(`ui.rating.ack.${value}`)}
      </p>
    );
  }

  return (
    <div className={cn("flex items-center gap-1", className)}>
      {CHOICES.map(({ id, Icon }) => (
        <button
          key={id}
          type="button"
          onClick={() => onRate(id)}
          aria-label={t(`ui.rating.${id}`)}
          className={cn(
            "inline-flex items-center justify-center rounded-portrait text-ink-muted",
            touchTarget,
            motionStandard,
            focusRing,
            "hover:bg-surface-sunken hover:text-ink-primary",
          )}
        >
          <Icon aria-hidden="true" strokeWidth={ICON_STROKE} className="h-4 w-4" />
        </button>
      ))}
    </div>
  );
}
