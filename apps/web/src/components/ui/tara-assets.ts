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
 * ── What is here, and what is deliberately not ──────────────────────────────
 * Stills only. **Cinemagraphs are DEFERRED POST-BETA — a scheduling decision,
 * not a gap in the delivery.** §25.2's twelve loops and §0.12's idle-breathing
 * allowance both stand; they are simply not part of the beta scope. Until then
 * TaraPresence mounts no video and every surface renders the still, which is
 * already how the component behaves when `cinemagraph*` is absent. Loops arrive
 * by filling those two fields per state — no component change, and the
 * screenshot baselines will show the change as a reviewable diff.
 *
 * Anyone reading this file and finding no `cinemagraphH265`/`cinemagraphVp9`
 * should stop here rather than treating it as work to be picked up:
 * `TARA_MOTION_STATUS` below is the record.
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
 * borrow the calmest available frames. Purpose-made replacements are in
 * generation and land before M8 ships (`TARA_APPROXIMATE_STATES_PENDING`), at
 * which point the flags come off. Anything reading this manifest can see which
 * states are provisional instead of assuming all twelve are exact.
 */

import type { PresenceState } from "./_util";

export const TARA_ASSET_STATUS: "placeholder" | "generated" = "generated";

/**
 * Why there are no loops. Deferred, not missed — see the header.
 *
 * When cinemagraphs land, fill `cinemagraphH265`/`cinemagraphVp9` per state and
 * set `deferred: false`; `TaraPresence` needs no change, and §0.12 still allows
 * exactly one loop (her idle breathing) and nothing else.
 */
export const TARA_MOTION_STATUS = {
  cinemagraphs: "deferred",
  until: "post-beta",
  deferred: true,
  reason: "scheduling decision, 9 Aug 2026 — the beta ships on stills",
} as const;

/**
 * The two states carrying a borrowed frame rather than a purpose-made one.
 * Replacements are in generation and land **before M8 ships**; until they do,
 * `approximate: true` on those entries is the honest signal, and this is the
 * record that it is temporary rather than the permanent state of the kit.
 */
export const TARA_APPROXIMATE_STATES_PENDING = {
  states: ["concern_kind", "safety_still"],
  status: "in generation",
  due: "before M8 ships",
} as const;

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

/**
 * §4.3's twelve states → the twelve delivered masters.
 *
 * The masters were named against the invented state list this file used to
 * carry, so five of the slugs no longer read as the state they serve. The
 * SLUGS are deliberately left alone — they name files on disk built from
 * ~30MB escrow masters (§22.16), and renaming a hundred derivatives to make a
 * mapping table look tidier is a large diff that changes no pixel.
 *
 * Each pairing below was chosen by looking at the master, not by matching
 * names, because a wrong mapping puts a festive portrait on a safety screen:
 *
 *   welcome          `smile`         a smile arriving — light, just forming (§4.3's own words)
 *   thoughtful       `thoughtful`    steady, direct
 *   calm_guidance    `reading`       gaze down over a page. §10's S14 template puts
 *                                    state 5 on read-aloud, and this is that frame
 *   encouragement    `full_smile`    warm, open, daylight — encouraging, not celebratory
 *   celebration      `celebration`   §4.3's "full warm smile", standing, gold sari
 *   profile_portrait `warm_neutral`  the canonical lamp-lit portrait
 */
export const TARA_ASSETS: Record<PresenceState, TaraAsset> = {
  welcome: asset("smile"),
  listening: asset("listening"),
  speaking_soft: asset("speaking_soft"),
  thoughtful: asset("thoughtful"),
  calm_guidance: asset("reading"),
  // no "concerned but kind" frame in the delivered set — closest calm frame
  concern_kind: asset("concerned_kind", true),
  encouragement: asset("full_smile"),
  celebration: asset("celebration"),
  night: asset("night"),
  festival: asset("festival"),
  // §29.5 puts state 11 only in the chat header; the takeover screen carries no
  // portrait at all. This is the least intense frame available, not a shot for it.
  safety_still: asset("safety", true),
  profile_portrait: asset("warm_neutral"),
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
