"use client";

/**
 * §28.1: "browser back closes topmost sheet/overlay before popping routes."
 *
 * A hook rather than a change to `Sheet`/`Modal`, for two reasons. The
 * components are presentational and already own focus, escape and the scrim;
 * history is a NAVIGATION concern and belongs with the screen that decided to
 * open the overlay. And the same rule has to cover overlays that are not
 * Sheets — the S43 permission explainers, the paywall panel, the call overlay —
 * so it cannot live inside one component's file.
 *
 * The mechanism: opening pushes a history entry that belongs to the overlay, so
 * the next Back pops THAT instead of the route. Closing any other way (the
 * close button, Escape, a confirm) removes the entry again, or Back would need
 * two presses to leave the screen — which reads as a stuck page.
 */

import { useEffect, useRef } from "react";

const MARKER = "sitaraOverlay";

export function useCloseOnBack(open: boolean, onClose: () => void): void {
  const closedByBack = useRef(false);

  useEffect(() => {
    if (!open) return;
    closedByBack.current = false;
    window.history.pushState({ [MARKER]: true }, "");

    const onPop = () => {
      // The entry is already gone — the browser popped it. Just close.
      closedByBack.current = true;
      onClose();
    };
    window.addEventListener("popstate", onPop);

    return () => {
      window.removeEventListener("popstate", onPop);
      // Closed by a control rather than by Back: take our entry back off the
      // stack so the user's next Back leaves the SCREEN, as they expect.
      if (!closedByBack.current && window.history.state?.[MARKER]) {
        window.history.back();
      }
    };
  }, [open, onClose]);
}
