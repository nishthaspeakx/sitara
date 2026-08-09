/**
 * §28.2's "sky gradient matching local time", from tokens that already exist.
 *
 * ── Why the gradient carries no text ───────────────────────────────────────
 *
 * The first cut painted the header's date and tithi line directly on the
 * gradient and declared the pairings in `contrast-matrix.json`. `token-lint`
 * rejected six of them, and every rejection was a real defect rather than a
 * strict threshold:
 *
 *   · `ink-muted` on `gold-soft` is 3.33:1 and on `line` is 3.75:1 — the tithi
 *     line would have failed AA on two of the four bands in the LIGHT theme.
 *   · `gold-soft` is a LIGHT fill in the night theme too (#EAD9A6, meant to sit
 *     under `on-gold`), so a morning band there put light ink on a cream
 *     background at 1.17:1.
 *   · `text-inverse` means "the opposite of this theme's ink", so on a fixed
 *     dark night sky it is cream in the light theme and NAVY in the night one —
 *     1.02:1, invisible, in exactly the theme the night band exists for.
 *
 * A gradient is the worst surface to measure against anyway: the value under a
 * given word depends on where the word landed. So the sky is a decorative strip
 * ABOVE the content, and every string sits on solid `bg-canvas` — a pairing the
 * matrix already declares and `token-lint` already verifies in both themes.
 * §28.2 asks the sky to say what time it is, not to be read.
 *
 * No colour is added to the frozen §24.2/§34.8 palette: every stop below is an
 * existing token, and each moves with the theme because it is a CSS variable.
 */

import type { TimeBand } from "@sitara/schemas";

/**
 * The strip, per band. Two stops, always — more stops read as decoration.
 * Every band lands on `bg-canvas` so the strip dissolves into the page rather
 * than ending in a line.
 */
const BAND_SKY: Record<TimeBand, string> = {
  // Early: warmed light. `gold-soft` is a fill token and §0.13 keeps gold for
  // interactive/sacred/celebratory — a sunrise is the celebratory,
  // non-interactive surface it is allowed on.
  morning: "bg-gradient-to-b from-gold-soft to-bg-canvas",
  // Midday: flat and quiet, so nothing competes with the core card.
  afternoon: "bg-gradient-to-b from-surface to-bg-canvas",
  // The light turning. `line` is the palette's warm neutral in light and its
  // dim blue at night, so this band tracks the theme with one value.
  evening: "bg-gradient-to-b from-line to-bg-canvas",
  // §28.2's dusk takeover. S01's night sky, reused deliberately: the app's one
  // existing night sky should be the same night sky.
  night: "bg-gradient-to-b from-launch-sky-top to-bg-canvas",
};

/** How tall the strip is per band. Night gets more of it — the takeover is
 *  meant to be felt, and it is the only band with nothing above the fold to
 *  hurry past. */
const BAND_HEIGHT: Record<TimeBand, string> = {
  morning: "h-20",
  afternoon: "h-16",
  evening: "h-20",
  night: "h-28",
};

export interface SkyClasses {
  /** The decorative strip. Carries no text, by design — see the header above. */
  strip: string;
  height: string;
}

export function skyFor(band: TimeBand): SkyClasses {
  return { strip: BAND_SKY[band], height: BAND_HEIGHT[band] };
}
