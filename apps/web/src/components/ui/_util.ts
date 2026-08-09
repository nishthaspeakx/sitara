/**
 * Shared primitives for the §24.3 component library.
 *
 * Everything here is token-only (§24.2) and locale-agnostic: components never
 * hold a literal user-facing string, they hold a message KEY (§2.4).
 */

/** A key into the ICU catalogs in @sitara/i18n. Never a literal English string. */
export type MessageKey = string;

export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

/**
 * §29.4: "2px gold ring + 2px offset, visible in both themes, never removed."
 * `shadow-focus` paints the outer contour that carries WCAG 2.2 non-text
 * contrast — light gold is 2.26:1 on cream and cannot do it alone. See
 * packages/tokens/CLAUDE.md.
 */
export const focusRing =
  "outline-none focus-visible:outline focus-visible:outline-focus " +
  "focus-visible:outline-offset-focus focus-visible:outline-focus-ring focus-visible:shadow-focus";

/** §24.2: every interactive target is at least 44×44. */
export const touchTarget = "min-h-touch-target-min min-w-touch-target-min";

/** §29.4: form controls are 48px, label above (floating labels fail Indic scripts). */
export const controlHeight = "h-control-height";

/** §0.12 standard transition, collapsed by the reduced-motion token layer. */
export const motionStandard =
  "transition-[transform,opacity,background-color,border-color,box-shadow] " +
  "duration-standard ease-standard";

/** Icons are a single 1.5px-stroke rounded set on a 24px grid (§24.7). */
export const ICON_STROKE = 1.5;

/** The four sizes TaraPresence ships in (§24.3). */
export const TARA_SIZES = ["sm", "md", "lg", "full"] as const;
export type TaraSize = (typeof TARA_SIZES)[number];

/**
 * Tara's 12 presence states (§4.3), used by TaraPresence and the §29.5 usage
 * map. She is a photographic presence — never call this an avatar (glossary).
 */
export const TARA_STATES = [
  "warm_neutral",
  "listening",
  "speaking_soft",
  "smile",
  "full_smile",
  "thoughtful",
  "concerned_kind",
  "celebration",
  "night",
  "festival",
  "reading",
  "safety",
] as const;
export type TaraState = (typeof TARA_STATES)[number];

/**
 * §5.4/§34.7 — all five ConfidenceChip treatments. Never caution/danger colours.
 *
 * Re-exported from `@sitara/schemas` rather than declared here. These IDs are
 * the WIRE format — sitara-api serves them verbatim on every guidance payload —
 * and a second hand-written copy is exactly how they drifted: this file typed
 * `verified_limited`/`tradition_general` for a whole milestone while the API
 * served `verified_limited_birth_data`/`tradition_based_general`, so two of the
 * five states could never have rendered. `packages/schemas/src/confidence-states.json`
 * is the one source and `test_parity.py` fails on divergence.
 */
export { CONFIDENCE_STATES, type ConfidenceState } from "@sitara/schemas";
