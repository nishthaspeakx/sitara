"use client";

/**
 * §25.4's "Tara is typing… / Tara is listening…".
 *
 * Driven by §34.6 `presence.state` events, which the realtime service emits
 * from the pipeline's real §9 stage transitions. That is the whole reason this
 * takes a key rather than a boolean: the two labels are two different presence
 * states, not two guesses about elapsed time.
 *
 * **It stops when the pipeline stops reporting.** A stalled turn shows no
 * indicator — an animation that keeps running through a dead socket is the
 * same lie as a fake "online", which §25.4 already refuses.
 *
 * §0.12: the dots loop, so they carry `motion-reduce`/`motion-off` as well as
 * the token layer's collapsed durations.
 */

import { useTranslations } from "next-intl";

import { cn } from "@/components/ui/_util";

const DOT =
  "h-1.5 w-1.5 rounded-full bg-ink-muted animate-pulse motion-reduce:animate-none motion-off:animate-none";

export function TypingIndicator({
  labelKey,
}: {
  labelKey: "ui.ask.typing" | "ui.ask.listening";
}) {
  const t = useTranslations();
  return (
    <div
      data-testid="typing-indicator"
      className="flex w-fit items-center gap-2 rounded-card rounded-es-none border border-border-subtle bg-surface px-3 py-2"
    >
      <span aria-hidden="true" className="flex items-center gap-1">
        <span className={DOT} />
        <span className={cn(DOT, "[animation-delay:150ms]")} />
        <span className={cn(DOT, "[animation-delay:300ms]")} />
      </span>
      <span className="text-caption text-ink-muted">{t(labelKey)}</span>
    </div>
  );
}
