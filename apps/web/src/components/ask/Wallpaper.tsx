"use client";

/**
 * §25.4's chat wallpaper: "subtle constellation on cream; dusk variant at
 * night; per-festival wallpapers".
 *
 * Two rules carried over from `today/sky.ts`, for the same reasons it records
 * them at length:
 *
 * **No text sits on it.** The wallpaper is decorative and `aria-hidden`; every
 * word in the thread is on `bg-canvas` or inside a bubble, both of which the
 * §24.2 contrast matrix already verifies in both themes. A gradient is the
 * worst possible surface to measure a pairing against, because the value under
 * a given word depends on where the word landed.
 *
 * **No new colour.** The dusk variant reuses the app's one existing night sky
 * (`launch-sky-top`), because the app should have one night sky rather than
 * two that nearly match.
 *
 * The festival variant is deliberately NOT here. §25.4 lists per-festival
 * wallpapers and §2.3 makes festivals tradition-specific; a generic "festival
 * wallpaper" would be exactly the generic-Hindu-calendar mistake §25.6 item (4)
 * calls out. It ships with the festival art slots, not before them.
 */

import { cn } from "@/components/ui/_util";

export function Wallpaper({ night = false }: { night?: boolean }) {
  return (
    <div
      aria-hidden="true"
      data-testid="wallpaper"
      className={cn(
        "pointer-events-none absolute inset-0 overflow-hidden",
        night
          ? "bg-gradient-to-b from-launch-sky-top to-bg-canvas"
          : "bg-gradient-to-b from-surface to-bg-canvas",
      )}
    >
      <svg
        viewBox="0 0 390 844"
        preserveAspectRatio="xMidYMid slice"
        className="h-full w-full opacity-30"
        role="presentation"
      >
        <g className="stroke-border-subtle" strokeWidth="1" fill="none" strokeLinecap="round">
          <path d="M40 120 L96 88 L150 132 L214 96" />
          <path d="M268 220 L318 190 L356 236" />
          <path d="M52 430 L110 470 L168 438 L222 486" />
          <path d="M296 604 L340 566" />
          <path d="M64 720 L128 690 L186 730" />
        </g>
        <g className="fill-gold-soft">
          {[
            [40, 120],
            [96, 88],
            [150, 132],
            [214, 96],
            [268, 220],
            [318, 190],
            [356, 236],
            [52, 430],
            [110, 470],
            [168, 438],
            [222, 486],
            [296, 604],
            [340, 566],
            [64, 720],
            [128, 690],
            [186, 730],
          ].map(([cx, cy]) => (
            <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r="2" />
          ))}
        </g>
      </svg>
    </div>
  );
}
