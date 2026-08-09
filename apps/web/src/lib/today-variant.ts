/**
 * §32.1's precedence rule — the ONE implementation.
 *
 * "Banners/pills stack top-down in fixed priority, max 2 banners + 1 pill
 * visible: 1 Safety/system (never co-renders with anything) · 2 Payment-grace
 * (amber) · 3 Travel · 4 Festival (the only surface above the core card;
 * suppressed if 2 banners already shown — festival then renders as the
 * core-card accent instead) · 5 Trial pill · 6 Birth-time chip (suppressed
 * whenever any banner shows). Night takeover replaces the whole stack except
 * payment-grace. Free-variant locking overrides density."
 *
 * That paragraph is six interacting rules, and the reason it lives in one pure
 * module rather than inside the JSX is that the interactions are where it goes
 * wrong. The worst case §32.1 itself names — grace + travel + festival + trial
 * — is a morning where three of the six rules fire at once, and it is exactly
 * the morning nobody has in front of them while writing a component.
 *
 * The server deliberately does not do this. `today.json` has no `variant`
 * field: the payload carries STATE, and the rule reading it lives with the
 * layout it governs. Two implementations would disagree on precisely the
 * crowded morning the rule exists for.
 */

import {
  timeBand,
  type TimeBand,
  type TodayPayload,
  type TodayState,
} from "@sitara/schemas";

/** §28.2's sixteen. The order is the spec's own enumeration order. */
export const TODAY_VARIANTS = [
  "first_session",
  "first_morning",
  "normal_morning",
  "afternoon",
  "evening",
  "night",
  "festival",
  "birthday",
  "travel",
  "missing_birth_time",
  "offline",
  "provider_degraded",
  "trial",
  "premium",
  "free",
  "payment_grace",
] as const;
export type TodayVariant = (typeof TODAY_VARIANTS)[number];

/**
 * Recorded states that are not one of §28.2's sixteen.
 *
 * `worst_case` is §32.1's own named screenshot combination
 * (grace + travel + festival + trial). It is the single most useful thing to
 * put in front of a person — four rules firing at once — so the dev switcher
 * offers it, while `TODAY_VARIANTS` keeps meaning sixteen.
 */
export const EXTRA_FIXTURES = ["worst_case"] as const;

/** What may sit above the core card, in §32.1's fixed priority order. */
export type BannerKind = "safety" | "payment_grace" | "travel" | "festival" | "offline";

export interface TodayChrome {
  /** The variant name — for `data-variant`, analytics and the dev switcher. */
  variant: TodayVariant;
  band: TimeBand;
  /** After 20:00 local: "the whole tab transforms" (§28.2). */
  night: boolean;
  /** At most two, already in priority order (§32.1). */
  banners: BannerKind[];
  /** At most one. The trial day-counter, or nothing. */
  trialPill: number | null;
  /** §28.2's dismissible "add birth time" chip. */
  birthTimeChip: boolean;
  /**
   * §32.1: a festival that lost its banner slot "renders as the core-card
   * accent instead" — it is never simply dropped.
   */
  festivalAccent: boolean;
  /** §28.2's Free variant: personal cards locked behind one calm CTA. */
  locked: boolean;
}

export interface ChromeInput {
  state: TodayState;
  localTime: string;
  status: TodayPayload["status"];
  /** The client's own condition — a failed fetch over a cached payload. */
  offline?: boolean;
  /** §22.9 L3+ takeover. No safety surface exists yet; the slot does. */
  safety?: boolean;
}

/** §32.1: "max 2 banners". */
export const MAX_BANNERS = 2;

export function resolveChrome(input: ChromeInput): TodayChrome {
  const { state, localTime, status, offline = false, safety = false } = input;
  const band = timeBand(localTime);
  const night = band === "night";

  // ── the banner stack ────────────────────────────────────────────────────
  //
  // Built in §32.1's declared order and then truncated, so "which two won" is
  // a consequence of the priority rather than a second decision that could
  // disagree with it.
  let banners: BannerKind[] = [];
  if (safety) {
    // "never co-renders with anything" — not merely first.
    banners = ["safety"];
  } else {
    const candidates: BannerKind[] = [];
    if (state.plan === "grace") candidates.push("payment_grace");
    if (state.travel.active) candidates.push("travel");
    if (offline) candidates.push("offline");
    if (state.festival) candidates.push("festival");
    banners = candidates.slice(0, MAX_BANNERS);
  }

  // "Night takeover replaces the whole stack EXCEPT payment-grace." A payment
  // that needs attention is the one thing that must survive the dusk change —
  // it is the only banner with a consequence attached to ignoring it.
  if (night && !safety) {
    banners = banners.filter((b) => b === "payment_grace");
  }

  const festivalShown = banners.includes("festival");

  // ── the pill and the chip ───────────────────────────────────────────────
  const trialPill = safety || night ? null : state.trial_day;
  // §32.1: "suppressed whenever any banner shows". Not "when the stack is
  // full" — the chip is the lowest-priority thing on the screen and it yields
  // to anything.
  const birthTimeChip = state.birth_time_missing && banners.length === 0 && !safety;

  return {
    variant: pickVariant({ state, band, status, offline }),
    band,
    night,
    banners,
    trialPill,
    birthTimeChip,
    // A festival exists but did not get a banner: §32.1 sends it to the core
    // card rather than dropping it.
    festivalAccent: Boolean(state.festival) && !festivalShown,
    locked: state.plan === "free",
  };
}

/**
 * Which of §28.2's sixteen this morning IS.
 *
 * One name, for `data-variant`, the screenshot matrix and analytics — the
 * chrome above is what actually renders, and a morning can be several variants
 * at once. The order below is "most specific first": a first session is a first
 * session whatever the clock says, and an offline screen is offline whatever
 * else is true of the payload it cached.
 */
function pickVariant(args: {
  state: TodayState;
  band: TimeBand;
  status: TodayPayload["status"];
  offline: boolean;
}): TodayVariant {
  const { state, band, status, offline } = args;

  if (offline) return "offline";
  if (state.first_session) return "first_session";
  if (status === "verified_core_cards" || status === "failed") return "provider_degraded";
  if (state.birth_time_missing) return "missing_birth_time";
  if (state.travel.active) return "travel";
  if (state.festival) return "festival";
  if (state.birthday) return "birthday";
  if (state.plan === "grace") return "payment_grace";
  if (state.plan === "free") return "free";
  if (state.first_morning) return "first_morning";
  if (state.trial_day !== null) return "trial";
  if (state.plan === "premium" && band === "morning") return "premium";

  // Whatever is left is simply the time of day.
  if (band === "night") return "night";
  if (band === "evening") return "evening";
  if (band === "afternoon") return "afternoon";
  return "normal_morning";
}

/**
 * §28.2's contextual cap, by density.
 *
 * The ranking engine already caps its OUTPUT by density; this is the render
 * side of the same rule, and it exists because §28.2 states the ceiling as a
 * layout property ("max 4 visible, 'more' expands"). Duplicating the number
 * would be a drift risk if the two could disagree — they cannot, because the
 * engine's cap is always ≤ this one and "more" only ever reveals what was
 * already sent.
 */
export const VISIBLE_CONTEXTUAL = 4;
