"use client";

/**
 * StoryRing — §24.3 / §25.5 / §30.6. States: unviewed · viewed · none.
 *
 * §30.6: Stories are a **P1 flag** and the ring is HIDDEN in P0. `enabled`
 * defaults to false so a P0 build renders the bare portrait even if a screen
 * forgets the flag — the safe default is the shipped one.
 */

import { useTranslations } from "next-intl";

import { TaraPresence } from "./TaraPresence";
import { cn, focusRing, motionStandard, type TaraSize, type TaraState } from "./_util";

export type StoryRingState = "unviewed" | "viewed" | "none";

export interface StoryRingProps {
  /** §30.6 P1 flag. False (P0) hides the ring entirely. */
  enabled?: boolean;
  state?: StoryRingState;
  size?: TaraSize;
  taraState?: TaraState;
  onOpen?: () => void;
  className?: string;
}

const RING: Record<Exclude<StoryRingState, "none">, string> = {
  unviewed: "border-gold",
  viewed: "border-border-subtle",
};

export function StoryRing({
  enabled = false,
  state = "none",
  size = "sm",
  taraState = "warm_neutral",
  onOpen,
  className,
}: StoryRingProps) {
  const t = useTranslations();
  const showRing = enabled && state !== "none";

  const portrait = <TaraPresence size={size} state={taraState} />;

  if (!showRing) {
    return <div className={className}>{portrait}</div>;
  }

  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label={t(`ui.story.${state}`)}
      className={cn(
        "rounded-portrait border-presence-ring p-presence-ring-gap",
        RING[state],
        motionStandard,
        focusRing,
        className,
      )}
    >
      {portrait}
    </button>
  );
}
