"use client";

/**
 * DEV ONLY — render the app inside an iPhone-17-sized viewport on a desktop.
 *
 * Sitara is a phone app. On a 1440px laptop it renders edge to edge, and every
 * judgement made against that — line length, tap targets, how much of the brief
 * is above the fold, whether the tab bar is reachable with a thumb — is a
 * judgement about a screen nobody has. This puts the real dimensions back.
 *
 * ── Why this is not a `<div>` with a width ─────────────────────────────────
 *
 * A wrapper alone does not contain an app. Three things escape it:
 *
 *  1. **Viewport units.** `100vh`/`100dvh` resolve against the BROWSER
 *     viewport, always — there is no way to scope them. Every screen root
 *     therefore measures `--app-vh` (see `globals.css`), which this component
 *     sets to the phone's height and which falls back to `100dvh` unframed.
 *
 *  2. **`position: fixed` descendants.** Fixed positions against the viewport,
 *     not an ancestor — so the Sheet, the Modal, the Toast and the launch
 *     sequence would all cover the laptop rather than the phone.
 *
 *     The fix is to make the phone a CONTAINING BLOCK for fixed descendants.
 *     `contain: layout paint` does that, and it is chosen over the more common
 *     `transform: translateZ(0)` for two reasons: paint containment also clips
 *     descendants to the border box, which is exactly the behaviour a phone
 *     screen wants and which the rounded corners need anyway; and a transform
 *     promotes the subtree to its own compositing layer, which on several GPUs
 *     changes subpixel text rendering — so the frame would subtly alter the
 *     thing it exists to let you judge.
 *
 *  3. **`env(safe-area-inset-*)`.** Set by the user agent and unassignable in
 *     CSS. A framed app would read the laptop's insets, which are zero, and
 *     draw its header under the Dynamic Island. `--app-safe-*` defaults to
 *     `env()` and is overridden here.
 *
 * **Portals are NOT a problem in this codebase and that was checked, not
 * assumed:** there is no `createPortal` and no `document.body` reference in
 * `apps/web/src`. `Sheet` and `Modal` render inline, which is why (2) is
 * sufficient. If a portal is ever added it must target `#device-frame-portal`
 * below, and `tests/device-frame.spec.ts` will fail until it does.
 *
 * ── When it is active ──────────────────────────────────────────────────────
 *
 * All of: the build-time flag is `1`, the window is at least 900px wide, and
 * the pointer is not coarse. On a phone, in CI, and in any production build it
 * renders **nothing at all** — not a wrapper, not a class, not a style tag —
 * and `tests/device-frame.spec.ts` asserts that from the DOM.
 */

import { useEffect, useState, type ReactNode } from "react";

/** iPhone 17 / 6.3", logical CSS pixels. */
export const DEVICE = {
  width: 402,
  height: 874,
  radius: 55,
  safeTop: 59,
  safeBottom: 34,
} as const;

/** Below this the frame would be bigger than the window it sits in. */
const MIN_WINDOW_WIDTH = 900;

/**
 * Inlined at BUILD time by Next. A production build with the variable unset
 * compiles this to `"undefined" === "1"` → false, so the whole component
 * short-circuits before any hook runs and the bundle keeps nothing live.
 */
const FLAG_ON = process.env.NEXT_PUBLIC_DEVICE_FRAME === "1";

function desktopEnough(): boolean {
  if (typeof window === "undefined") return false;
  if (window.innerWidth < MIN_WINDOW_WIDTH) return false;
  // A coarse pointer is a touch device — which is real hardware, where the
  // frame would be drawing a phone inside a phone.
  if (window.matchMedia?.("(pointer: coarse)").matches) return false;
  // `?frame=0` — one page load, for comparing against the raw viewport.
  return new URLSearchParams(window.location.search).get("frame") !== "0";
}

export function DeviceFrame({ children }: { children: ReactNode }) {
  // Not `useState(desktopEnough())`: the server renders unframed and a client
  // that decided otherwise on first paint is a hydration mismatch. So the app
  // mounts unframed and the frame appears on the first effect — one frame of
  // full-width, in dev only, in exchange for a tree that always hydrates.
  const [framed, setFramed] = useState(false);
  const [enabled, setEnabled] = useState(true);

  useEffect(() => {
    if (!FLAG_ON) return;
    const decide = () => setFramed(desktopEnough());
    decide();
    window.addEventListener("resize", decide);
    return () => window.removeEventListener("resize", decide);
  }, []);

  // The zero-DOM path. Deliberately before any markup: a production build
  // returns children untouched, with no wrapper element to inspect.
  if (!FLAG_ON || !framed || !enabled) return <>{children}</>;

  return (
    <div
      data-testid="device-frame-backdrop"
      className="fixed inset-0 z-0 flex items-center justify-center overflow-auto bg-surface-sunken p-8"
      style={
        {
          // Tokens only (§24.2). The backdrop needs a surface DISTINCT from
          // the app's own `bg-canvas` or the phone has no visible edge —
          // `surface-sunken` is the token for a recessed plane, which is
          // exactly the relationship a desk behind a phone has. (There is no
          // `canvas-alt` token; inventing one for chrome would put a colour
          // in the frozen palette for a dev aid.)
          "--app-vh": `${DEVICE.height}px`,
          "--app-safe-top": `${DEVICE.safeTop}px`,
          "--app-safe-bottom": `${DEVICE.safeBottom}px`,
        } as React.CSSProperties
      }
    >
      <div
        data-testid="device-frame"
        className="relative shrink-0 bg-bg-canvas shadow-sheet ring-1 ring-border-strong"
        style={{
          width: DEVICE.width,
          height: DEVICE.height,
          borderRadius: DEVICE.radius,
          // (2) above. Containing block for fixed descendants + clip to the
          // border box, without a compositing layer.
          contain: "layout paint",
          // `contain: paint` clips at the border box; the radius makes that
          // clip follow the corners.
          overflow: "hidden",
        }}
      >
        {/* The app's scroller. `overscroll-contain` stops a scroll that
            reaches the end of the app from rubber-banding the backdrop
            behind it — the tell that you are looking at a page, not a phone. */}
        <div
          data-testid="device-frame-viewport"
          className="h-full w-full overflow-y-auto overscroll-contain"
        >
          {children}
          {/* Portal target. Nothing uses it today (see the header); it exists
              so that when something does, there is a node INSIDE the phone to
              aim at rather than `document.body`. */}
          <div id="device-frame-portal" />
        </div>

        {/* Dynamic Island. `pointer-events-none` so it never eats a tap meant
            for the app underneath — it is chrome, not UI. */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute left-1/2 top-[11px] h-[37px] w-[125px] -translate-x-1/2 rounded-full bg-brand-navy-deep"
        />
        {/* Home indicator. */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute bottom-[8px] left-1/2 h-[5px] w-[139px] -translate-x-1/2 rounded-full bg-ink-muted opacity-60"
        />
      </div>

      {/* Dev toggle. Outside the phone, memory only — no localStorage, so it
          cannot survive into a state somebody later debugs from. */}
      <button
        type="button"
        data-testid="device-frame-toggle"
        onClick={() => setEnabled(false)}
        className="fixed bottom-4 right-4 rounded-chip border border-border-subtle bg-surface px-3 py-2 text-caption text-ink-secondary shadow-sheet"
      >
        Full width
      </button>
    </div>
  );
}
