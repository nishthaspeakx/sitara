/**
 * §0.11 — which of the five launch paths runs, and how long it takes.
 *
 * Pure and DOM-free so the decision is testable without a canvas: everything
 * the choice depends on (reduced-motion, first-ever visit, device tier, an
 * explicit override) arrives as an argument.
 *
 * This module is screen-local, not a §24.3 component. It computes numbers and
 * draws pixels; it has no DOM surface, no states in the Figma sense, and no
 * second caller — putting it in `components/ui` would add a 50th entry to a
 * library the spec fixes at 49, for something that is not a component.
 */

/** §0.11's five paths, re-exported from the analytics taxonomy that names them. */
export { LAUNCH_PATHS, type LaunchPath, type DeviceTier } from "@/lib/analytics";

import type { DeviceTier, LaunchPath } from "@/lib/analytics";

/**
 * The full sequence's six phases, in milliseconds from frame one.
 *
 * These ARE §0.11's storyboard table — the acceptance criterion is "all timings
 * within ±80ms of spec on the device matrix", so they are transcribed rather
 * than approximated, and a change here is a change to the spec.
 */
export const FULL_PHASES = [
  { id: "deep_sky", start: 0, end: 600 },
  { id: "gathering", start: 600, end: 1800 },
  { id: "alignment", start: 1800, end: 2800 },
  { id: "bright_star", start: 2800, end: 3600 },
  { id: "tara_arrives", start: 3600, end: 4600 },
  { id: "wordmark_settle", start: 4600, end: 5500 },
] as const;

export const FULL_DURATION_MS = 5500;

/** Short form: phases 1+3 compressed → wordmark → dissolve. No Tara, no voice. */
export const SHORT_PHASES = [
  { id: "compressed", start: 0, end: 1200 },
  { id: "wordmark_settle", start: 1200, end: 1800 },
  { id: "dissolve", start: 1800, end: 2200 },
] as const;

export const SHORT_DURATION_MS = 2200;

/** §0.11's reduced-motion and low-bandwidth form: one 1.2s crossfade. */
export const STATIC_DURATION_MS = 1200;

/** §0.11: "skip works from frame one post-first-launch and lands on Home in ≤300ms". */
export const SKIP_LANDING_BUDGET_MS = 300;

/** §0.11: "a subtle 'skip' affordance appearing at 1s". */
export const SKIP_AFFORDANCE_AT_MS = 1000;

/** Particle counts. §0.11: "max 60 particles (full) / 20 (short)". */
export const PARTICLES = { full: 60, short: 20, static: 0 } as const;

/** §0.11: "if the first 500ms drop below 24fps, the engine downgrades live". */
export const FPS_PROBE_MS = 500;
export const FPS_FLOOR = 24;

export function durationFor(path: LaunchPath): number {
  switch (path) {
    case "full":
      return FULL_DURATION_MS;
    case "short":
      return SHORT_DURATION_MS;
    default:
      // reduced_motion and static are the same 1.2s crossfade; `skipped` is
      // measured from frame one to the landing, not from a fixed length.
      return STATIC_DURATION_MS;
  }
}

export interface LaunchContext {
  prefersReducedMotion: boolean;
  /** False on the first-ever visit — §0.11 precaches AFTER first paint. */
  assetsPrecached: boolean;
  /** True once any launch has completed, which is what unlocks skip. */
  hasLaunchedBefore: boolean;
  /** True when a full ceremony has already run today. */
  ceremonySeenToday: boolean;
  tier: DeviceTier;
}

/**
 * §0.11's device tiering, "by `deviceMemory`/frame-probe".
 *
 * `deviceMemory` is Chromium-only and absent on Safari, which is most of the
 * diaspora corridor. Absent means tier B, never tier A: guessing capable on no
 * evidence spends the frame budget of a device we know nothing about, and the
 * live fps probe is what corrects an under-estimate a moment later.
 */
export function tierFrom(deviceMemory: number | undefined, cores: number | undefined): DeviceTier {
  if (deviceMemory === undefined && cores === undefined) return "b";
  if ((deviceMemory ?? 4) <= 2 || (cores ?? 4) <= 4) return "c";
  if ((deviceMemory ?? 4) >= 8) return "a";
  return "b";
}

/**
 * The path, before any live downgrade.
 *
 * Order matters and each rung is §0.11's own:
 *
 * 1. reduced motion wins over everything — an accessibility preference is not
 *    a performance hint to be weighed against others.
 * 2. a first-ever visit gets the static form, because the 220KB of assets are
 *    precached AFTER first paint and are not local yet.
 * 3. a ceremony already seen today gets the short form. §0.11 fixes what each
 *    form IS but not when the short one runs; §0.19's "supported, not
 *    controlled" decides it — a 5.5s ceremony on every app open is the app
 *    asking for attention rather than giving it.
 * 4. otherwise the full sequence, which is the point of the thing.
 *
 * Tier is deliberately NOT a rung. §0.11 gives tier C fewer particles and a
 * pre-baked bloom inside the full form; it does not demote the narrative.
 */
export function selectPath(context: LaunchContext): LaunchPath {
  if (context.prefersReducedMotion) return "reduced_motion";
  if (!context.assetsPrecached) return "static";
  if (context.ceremonySeenToday) return "short";
  return "full";
}

export function skipAllowed(context: LaunchContext): boolean {
  // §0.11: "skippable by tap/Enter/Escape from first frame (after first launch)".
  return context.hasLaunchedBefore;
}

export function particleCount(path: LaunchPath, tier: DeviceTier): number {
  if (path === "reduced_motion" || path === "static" || path === "skipped") return 0;
  const base = path === "full" ? PARTICLES.full : PARTICLES.short;
  // §0.11: "tier C (low-end) gets 20 particles".
  return tier === "c" ? Math.min(base, PARTICLES.short) : base;
}

/**
 * The seven-star "S̄" asterism — §0.11's fixed brand constellation.
 *
 * Unit coordinates in a 0–1 box so the shape is resolution-independent; the
 * renderer maps them onto the viewport's shorter axis. Index 3 is the centre
 * star that blooms into Tara in phase 4.
 */
export const CONSTELLATION: ReadonlyArray<readonly [number, number]> = [
  [0.72, 0.18],
  [0.42, 0.14],
  [0.28, 0.32],
  [0.5, 0.47],
  [0.72, 0.62],
  [0.58, 0.8],
  [0.28, 0.78],
];

/** Which star blooms (§0.11 phase 4: "Centre star scales 1→2.4×"). */
export const BLOOM_STAR_INDEX = 3;
