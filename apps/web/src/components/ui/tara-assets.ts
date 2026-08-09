/**
 * Tara's asset manifest (§4, §25.2 as amended by CC-008, §29.5).
 *
 * ── What Tara is ────────────────────────────────────────────────────────────
 * Tara's likeness is **AI-GENERATED AND EXCLUSIVELY OWNED BY SITARA. SHE IS NOT
 * A REAL PERSON AND NOT A LICENSED HUMAN MODEL.** CC-008 supersedes §25.2's
 * "real photoshoot with a licensed face model" baseline. Consequences that bind
 * this file and everything that reads it:
 *
 *   · The permanent "Tara · AI guide" disclosure (§25.2) stays mandatory
 *     wherever her name or face appears. TaraPresence renders it from
 *     `ui.tara.ai_label`; no surface may drop it.
 *   · No asset name, alt text, caption, or marketing copy may describe her as a
 *     real person, a photograph of someone, a model, or a licensed likeness.
 *     `tests/tara-disclosure.spec.ts` enforces this over the catalogs and the
 *     component source, so the rule fails CI rather than relying on review.
 *   · She is still never called an avatar (glossary), and §29.5's usage map is
 *     unchanged: no Tara on error, fatal, safety-takeover or support surfaces.
 *
 * ── What is here ────────────────────────────────────────────────────────────
 * Stills only. The delivered kit carries no cinemagraph loops, so TaraPresence
 * never mounts a video and every surface renders the still — which is already
 * how the component behaves when `cinemagraph*` is absent. Loops join later by
 * filling those fields; no component changes.
 *
 * Responsive sets are produced by `scripts/build-tara-assets.mjs` from masters
 * that are NOT committed (~30MB PNGs — escrow material under §22.16, not repo
 * material). Circle widths serve TaraPresence sm/md/lg at up to 3× DPR;
 * portrait widths serve the full-bleed call layout.
 *
 * ── Mapping fidelity, stated honestly ───────────────────────────────────────
 * Each state was mapped by looking at every master against §29.5's surface
 * assignments, not by matching filenames. Two are approximate and are marked
 * `approximate: true` below: the delivered set contains no frame that reads as
 * "concerned but kind", and none neutral enough for the safety surface. They
 * borrow the calmest available frames. Anything reading this manifest can see
 * which states are provisional instead of assuming all twelve are exact.
 */

import type { TaraState } from "./_util";

export const TARA_ASSET_STATUS: "placeholder" | "generated" = "generated";

/** How the likeness was produced. Read by the disclosure test and the docs. */
export const TARA_LIKENESS = {
  origin: "ai-generated",
  ownership: "exclusive",
  isRealPerson: false,
  isLicensedModel: false,
  disclosureKey: "ui.tara.ai_label",
  changeControl: "CC-008",
} as const;

/** Widths emitted by the pipeline. Keep in step with build-tara-assets.mjs. */
export const CIRCLE_WIDTHS = [168, 288, 480] as const;
export const PORTRAIT_WIDTHS = [720, 1080, 1440] as const;

export interface TaraAsset {
  /** Default src — the mid circle width, so a no-srcset client still gets a sane file. */
  poster: string;
  /** `srcSet` for the circular sizes, WebP then JPEG fallback. */
  circleWebp: string;
  circleJpeg: string;
  /** `srcSet` for the full-bleed portrait layout. */
  portraitWebp: string;
  portraitJpeg: string;
  /** True where the frame is the closest available rather than a purpose-shot state. */
  approximate?: boolean;
  /** H.265 loop. Absent — the delivered kit is stills only. */
  cinemagraphH265?: string;
  /** VP9 loop. Absent — the delivered kit is stills only. */
  cinemagraphVp9?: string;
}

const srcSet = (slug: string, widths: readonly number[], ext: string, full: boolean) =>
  widths.map((w) => `/tara/${slug}${full ? "-full" : ""}-${w}.${ext} ${w}w`).join(", ");

function asset(slug: string, approximate = false): TaraAsset {
  return {
    poster: `/tara/${slug}-288.jpg`,
    circleWebp: srcSet(slug, CIRCLE_WIDTHS, "webp", false),
    circleJpeg: srcSet(slug, CIRCLE_WIDTHS, "jpg", false),
    portraitWebp: srcSet(slug, PORTRAIT_WIDTHS, "webp", true),
    portraitJpeg: srcSet(slug, PORTRAIT_WIDTHS, "jpg", true),
    ...(approximate ? { approximate: true } : {}),
  };
}

export const TARA_ASSETS: Record<TaraState, TaraAsset> = {
  warm_neutral: asset("warm_neutral"),
  listening: asset("listening"),
  speaking_soft: asset("speaking_soft"),
  smile: asset("smile"),
  full_smile: asset("full_smile"),
  thoughtful: asset("thoughtful"),
  // no "concerned but kind" frame in the delivered set — closest calm frame
  concerned_kind: asset("concerned_kind", true),
  celebration: asset("celebration"),
  night: asset("night"),
  festival: asset("festival"),
  reading: asset("reading"),
  // §29.5 puts state 11 only in the chat header; the takeover screen carries no
  // portrait at all. This is the least intense frame available, not a shot for it.
  safety: asset("safety", true),
};

/** §25.5 Stories (P1, §30.6-gated) — not bound to a presence state. */
export const TARA_STORY_ASSETS = {
  "story-casual-reading": asset("story-casual-reading"),
  "story-chai": asset("story-chai"),
} as const;

/**
 * §29.5 — where Tara may NOT appear. She is never the face of failure, the
 * safety takeover screen is institutional calm with no portrait, and support is
 * humans, where her absence is the signal.
 */
export const TARA_FORBIDDEN_SURFACES = ["error", "fatal", "safety_takeover", "support"] as const;
