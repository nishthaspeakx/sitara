"use client";

/**
 * S01 — the launch sequence (§0.11, §29.1).
 *
 * Composes the §24.3 library for everything with a DOM surface (the skip
 * control is a `Button`, Tara is `TaraPresence`) and owns only the canvas,
 * which has none.
 *
 * Accessibility, per §0.11's own list:
 *   · every phase is decorative and `aria-hidden`; ONE live-region announcement
 *     carries the whole sequence ("Welcome to Sitara")
 *   · skippable by tap/Enter/Escape from frame one, after the first launch
 *   · focus is never trapped — the skip control is the only focusable thing
 *   · the star twinkle is 1.8s-period, far below WCAG 2.3's 3-flashes-per-second
 */

import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button, TaraPresence } from "@/components/ui";
import { track, type DeviceTier, type LaunchPath } from "@/lib/analytics";

import {
  LAUNCH_PATHS,
  SKIP_AFFORDANCE_AT_MS,
  durationFor,
  particleCount,
  selectPath,
  skipAllowed,
  tierFrom,
} from "./paths";
import { runSequence, type RunningSequence } from "./sequence";

/** Not auth material (§34.5) — a "have I seen this" flag and a date. */
const SEEN_KEY = "sitara.launch.seen";
const CEREMONY_KEY = "sitara.launch.ceremony_date";

function readFlags() {
  try {
    const today = new Date().toISOString().slice(0, 10);
    return {
      hasLaunchedBefore: localStorage.getItem(SEEN_KEY) === "1",
      ceremonySeenToday: localStorage.getItem(CEREMONY_KEY) === today,
      today,
    };
  } catch {
    // Private mode, or storage denied. Treat as a first visit: the static form
    // is the honest answer when we cannot know the assets are local.
    return { hasLaunchedBefore: false, ceremonySeenToday: false, today: "" };
  }
}

function isPath(value: string | null): value is LaunchPath {
  return value !== null && (LAUNCH_PATHS as readonly string[]).includes(value);
}

export function LaunchSequence({ onFinished }: { onFinished: () => void }) {
  const t = useTranslations();
  const locale = useLocale();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const runningRef = useRef<RunningSequence | null>(null);
  const reportedRef = useRef(false);
  /**
   * ONE skip implementation, shared by the gesture and the button.
   *
   * They were two, and the button's copy forgot to report — so a user who
   * tapped the visible affordance produced no `launch_sequence` event at all,
   * and §0.11's "skip works from frame one" acceptance had nothing to measure.
   * The flow suite caught it; a second copy is how it would come back.
   */
  const skipRef = useRef<() => void>(() => undefined);

  const [path, setPath] = useState<LaunchPath | null>(null);
  const [canSkip, setCanSkip] = useState(false);
  const [showSkip, setShowSkip] = useState(false);

  /** One event per launch, whatever happened. Guarded so a skip that races the
   *  natural end cannot report twice. */
  const report = useCallback(
    (taken: LaunchPath, tier: DeviceTier, downgraded: boolean) => {
      if (reportedRef.current) return;
      reportedRef.current = true;
      track("launch_sequence", {
        path: taken,
        duration_ms: runningRef.current?.elapsed() ?? durationFor(taken),
        tier,
        fps_downgraded: downgraded,
        // §0.11's web-audio reality: with no gesture signal the sequence runs
        // silent BY DESIGN, and Tara's welcome line moves to her first
        // on-screen interaction. The composition ("Sitara Arrival") is a W10
        // deliverable and does not exist yet, so today this is always silent —
        // recorded as a path, not as a failure.
        audio: "silent",
        locale,
      });
    },
    [locale],
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const flags = readFlags();
    const navigatorish = navigator as Navigator & { deviceMemory?: number };
    const tier = tierFrom(navigatorish.deviceMemory, navigator.hardwareConcurrency);
    const context = {
      prefersReducedMotion: window.matchMedia("(prefers-reduced-motion: reduce)").matches,
      assetsPrecached: flags.hasLaunchedBefore,
      hasLaunchedBefore: flags.hasLaunchedBefore,
      ceremonySeenToday: flags.ceremonySeenToday,
      tier,
    };

    // An explicit override, so §0.11's "±80ms on the device matrix" acceptance
    // can actually be measured on a real handset, and so all five paths are
    // screenshot-able. It selects an animation and nothing else.
    const override = new URLSearchParams(window.location.search).get("launch");
    const chosen = isPath(override) ? override : selectPath(context);
    setPath(chosen);
    setCanSkip(skipAllowed(context) || isPath(override));

    let downgraded = false;
    const finish = () => {
      try {
        localStorage.setItem(SEEN_KEY, "1");
        if (chosen === "full") localStorage.setItem(CEREMONY_KEY, flags.today);
      } catch {
        // Storage denied: every launch is then a first visit, which is the
        // static form. Correct, and never a crash on the first screen.
      }
      report(chosen, tier, downgraded);
      onFinished();
    };

    runningRef.current = runSequence({
      canvas,
      path: chosen,
      tier,
      particles: particleCount(chosen, tier),
      onDone: finish,
      onFpsDowngrade: () => {
        // Live downgrade: stop, and re-run as the static form. Reported as
        // `static` with the downgrade flag, because that IS what the user saw.
        downgraded = true;
        runningRef.current?.stop();
        setPath("static");
        runningRef.current = runSequence({
          canvas,
          path: "static",
          tier,
          particles: 0,
          onDone: () => {
            report("static", tier, true);
            onFinished();
          },
          onFpsDowngrade: () => undefined,
        });
      },
    });

    const affordance = window.setTimeout(() => setShowSkip(true), SKIP_AFFORDANCE_AT_MS);

    const skip = () => {
      if (!(skipAllowed(context) || isPath(override))) return;
      runningRef.current?.stop();
      report("skipped", tier, downgraded);
      try {
        localStorage.setItem(SEEN_KEY, "1");
      } catch {
        /* see above */
      }
      onFinished();
    };
    skipRef.current = skip;

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" || event.key === "Enter") skip();
    };
    // §0.11: skippable by TAP as well as by key, from frame one.
    canvas.addEventListener("click", skip);
    window.addEventListener("keydown", onKey);

    return () => {
      window.clearTimeout(affordance);
      canvas.removeEventListener("click", skip);
      window.removeEventListener("keydown", onKey);
      runningRef.current?.stop();
    };
  }, [onFinished, report]);

  return (
    <div
      className="fixed inset-0 overflow-hidden bg-brand-navy-deep"
      data-testid="launch-sequence"
      data-launch-path={path ?? "pending"}
    >
      <canvas ref={canvasRef} aria-hidden="true" className="h-full w-full" />

      {/* §0.11 phase 5 — the bloom resolves into Tara. Cinemagraphs are
          deferred post-beta (TARA_MOTION_STATUS), so TaraPresence renders her
          still, which is already its behaviour when no loop exists. */}
      {path === "full" ? (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <TaraPresence size="lg" state="smile" still showAiLabel />
        </div>
      ) : null}

      <p
        className="pointer-events-none absolute inset-x-0 bottom-24 text-center font-serif text-display text-launch-wordmark"
        aria-hidden="true"
      >
        {t("launch.wordmark")}
      </p>

      {/* The single announcement §0.11 allows. Everything above is decorative. */}
      <p className="sr-only" role="status" aria-live="polite">
        {t("launch.welcome")}
      </p>

      {canSkip && showSkip ? (
        <div className="absolute end-4 top-4">
          <Button variant="tertiary" onClick={() => skipRef.current()} data-testid="launch-skip">
            {t("launch.skip")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
