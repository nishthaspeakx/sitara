/**
 * Product analytics (§6 PostHog, §13 payload rules, §18 taxonomy).
 *
 * A typed emitter with a pluggable sink rather than a direct PostHog import,
 * for three reasons that are all §13 rather than architecture taste:
 *
 * * **The payload allowlist is enforced in code, not in review.** §13's logging
 *   middleware rule applies to analytics emission too — "no birth data, no
 *   message content, no names in any analytics or session-replay tool". Every
 *   event below declares its properties as a closed shape, and `sanitise`
 *   drops anything else rather than trusting call sites.
 * * **Session replay is off on the birth-detail screens**, which §13 names
 *   explicitly. That is a decision about WHICH SCREENS, so it lives beside the
 *   screen list, not in a vendor dashboard someone can toggle.
 * * **Consent gates the sink, not the call sites.** §13.EU requires consent
 *   mode before any non-essential analytics; a screen that had to ask before
 *   every `track()` would eventually forget once.
 *
 * With no key configured the sink is a no-op in production and a console line
 * in development — a missing analytics key is never a reason for a screen to
 * behave differently.
 */

// ---------------------------------------------------------------------------
// The events (§18's taxonomy — new events are PR-reviewed like error codes)
// ---------------------------------------------------------------------------

/**
 * §0.11's five launch paths. All five are reachable and the suite proves it:
 *
 *   full            5,500ms, six phases, 60 particles, Tara arrives
 *   short           2,200ms, 12 stars, no Tara, no voice
 *   reduced_motion  1.2s crossfade — no drift, no particles
 *   static          the first-ever visit (assets not yet precached) AND the
 *                   live downgrade when the first 500ms measures below 24fps
 *   skipped         tap/Enter/Escape, from frame one after the first launch
 *
 * One event with five values rather than five events, because every §0.11
 * acceptance question — did the timings hold, did the tier downgrade, did audio
 * play — is asked ACROSS the paths and would need a union of five schemas
 * otherwise.
 */
export const LAUNCH_PATHS = ["full", "short", "reduced_motion", "static", "skipped"] as const;
export type LaunchPath = (typeof LAUNCH_PATHS)[number];

/** §0.11's device tiers: A (capable) → C (Redmi Note-class). */
export type DeviceTier = "a" | "b" | "c";

export interface EventMap {
  /** §0.11 — one per launch, whichever path ran. */
  launch_sequence: {
    path: LaunchPath;
    duration_ms: number;
    tier: DeviceTier;
    /** True when the live fps probe dropped the sequence to the static form. */
    fps_downgraded: boolean;
    /** §0.11's web-audio reality: silent is a PATH, not a failure. */
    audio: "played" | "silent";
    locale: string;
  };
  /** §24.4 — "analytics step events" on every onboarding screen. */
  onboarding_step_viewed: { step: number; locale: string };
  onboarding_step_completed: { step: number; locale: string };
  /** §24.4 — drop-off is the number §0.17's ≥80% gate is measured from. */
  onboarding_abandoned: { step: number; locale: string };
  /** S13. `confidence` and `degrade_reason` are the two things worth knowing. */
  first_reading_shown: {
    status: string;
    confidence: string;
    degrade_reason: string | null;
    line_count: number;
    latency_ms: number;
    locale: string;
  };
}

export type EventName = keyof EventMap;

// ---------------------------------------------------------------------------
// §13 — the payload allowlist
// ---------------------------------------------------------------------------

/**
 * The ONLY property names that may leave the client, per event.
 *
 * A closed list rather than a denylist of PII field names: a denylist has to
 * predict what a future call site will name its variable, and the first one it
 * fails to predict is a birth date in an analytics warehouse.
 */
const ALLOWED: Record<EventName, readonly string[]> = {
  launch_sequence: ["path", "duration_ms", "tier", "fps_downgraded", "audio", "locale"],
  onboarding_step_viewed: ["step", "locale"],
  onboarding_step_completed: ["step", "locale"],
  onboarding_abandoned: ["step", "locale"],
  first_reading_shown: [
    "status",
    "confidence",
    "degrade_reason",
    "line_count",
    "latency_ms",
    "locale",
  ],
};

/**
 * §13's birth-detail screens. Session replay is disabled outright on these —
 * "session replay disabled on chat/onboarding birth-detail screens entirely".
 * Matched against the pathname, so a locale prefix does not defeat it.
 */
const REPLAY_FORBIDDEN = ["/start/birth", "/start/name", "/start/city", "/ask"];

export function replayAllowed(pathname: string): boolean {
  return !REPLAY_FORBIDDEN.some((surface) => pathname.includes(surface));
}

export function sanitise<E extends EventName>(
  event: E,
  props: EventMap[E],
): Record<string, unknown> {
  const allowed = ALLOWED[event];
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(props as Record<string, unknown>)) {
    if (allowed.includes(key)) out[key] = value;
    else if (process.env.NODE_ENV !== "production") {
      console.warn(`[analytics] dropped "${key}" from ${event} — not in the §13 allowlist`);
    }
  }
  return out;
}

// ---------------------------------------------------------------------------
// Sink
// ---------------------------------------------------------------------------

export type Sink = (event: string, props: Record<string, unknown>) => void;

let sink: Sink | null = null;

/** Tests and the PostHog bootstrap both install through here. */
export function setSink(next: Sink | null): void {
  sink = next;
}

/**
 * Every emission also fires a DOM event carrying the SANITISED payload.
 *
 * This is the observation hook the flow suite reads, and it is deliberately not
 * a test-only branch: a test that watched a special code path would prove that
 * path works and nothing about the one that ships. What it exposes has already
 * been through the §13 allowlist, so the hook cannot widen what leaves the
 * client — it can only show what already did.
 */
export const ANALYTICS_EVENT = "sitara:analytics";

export function track<E extends EventName>(event: E, props: EventMap[E]): void {
  const payload = sanitise(event, props);
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(ANALYTICS_EVENT, { detail: { event, props: payload } }));
  }
  if (sink) {
    sink(event, payload);
    return;
  }
  if (process.env.NODE_ENV === "development") {
    console.debug("[analytics]", event, payload);
  }
}
