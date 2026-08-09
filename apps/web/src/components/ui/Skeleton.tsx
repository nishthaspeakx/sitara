"use client";

/**
 * Skeleton set — §24.3 feedback: brief · chat · list.
 *
 * §24.6: skeletons MIRROR THE FINAL LAYOUT — no spinners on content surfaces.
 * Tara's breathing state doubles as conversational loading, which is why there
 * is no Tara skeleton here.
 *
 * The shimmer is a loop, so it stops under reduced motion (§0.12) and the
 * skeleton stays as a static block — still informative, just not moving.
 */

import { useTranslations } from "next-intl";

import { cn } from "./_util";

export type SkeletonVariant = "brief" | "chat" | "list";

function Bar({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "block rounded-chip bg-surface-sunken",
        "motion-safe:animate-pulse motion-reduce:animate-none motion-off:animate-none",
        className,
      )}
    />
  );
}

export interface SkeletonProps {
  variant: SkeletonVariant;
  /** How many repeats of the unit to draw. */
  count?: number;
  className?: string;
}

export function Skeleton({ variant, count = 3, className }: SkeletonProps) {
  const t = useTranslations();
  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy="true"
      className={cn("flex flex-col gap-3", className)}
    >
      <span className="sr-only">{t("ui.loading")}</span>
      {Array.from({ length: count }, (_, i) => (
        <div key={i} aria-hidden="true">
          {variant === "brief" ? (
            <div className="flex flex-col gap-2 rounded-card border border-border-subtle bg-surface p-4">
              <div className="flex items-center gap-3">
                <Bar className="h-8 w-8 rounded-portrait" />
                <Bar className="h-4 w-1/3" />
              </div>
              <Bar className="h-4 w-full" />
              <Bar className="h-4 w-4/5" />
            </div>
          ) : null}

          {variant === "chat" ? (
            <div className={cn("flex", i % 2 === 0 ? "justify-start" : "justify-end")}>
              <Bar className={cn("h-12 rounded-card", i % 2 === 0 ? "w-3/5" : "w-2/5")} />
            </div>
          ) : null}

          {variant === "list" ? (
            <div className="flex items-center gap-3 border-b border-border-subtle py-3">
              <Bar className="h-6 w-6 rounded-portrait" />
              <div className="flex flex-1 flex-col gap-2">
                <Bar className="h-4 w-1/2" />
                <Bar className="h-3 w-1/3" />
              </div>
            </div>
          ) : null}
        </div>
      ))}
    </div>
  );
}
