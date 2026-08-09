/**
 * The Tamil-length pseudo-locale (§24.3).
 *
 * "Every component: all 8 locales rendered in Figma via a pseudo-locale +
 * longest-string test (German-length rule replaced with Tamil-length rule —
 * Tamil runs ~1.4× English)."
 *
 * This is the code-side half of that rule. It is deliberately NOT a catalog in
 * packages/i18n: §2.4 admits a locale only through the §12 admin locale gate
 * with a signed 100% checklist, and a pseudo-locale sitting next to the real
 * ones is exactly how a fake language ships by accident. It lives here, in the
 * Storybook harness, and is generated from `en` at build time.
 *
 * What it tests:
 *  · length     — every string padded to ~1.4× its English length
 *  · script     — real Tamil glyphs, so shaping and the §24.2 Tamil tuning
 *                 (1.05× size, 1.8 line-height, +0.01em tracking) are exercised
 *  · ICU safety — placeholders and plural forms are preserved untouched, so a
 *                 component that breaks on a padded string breaks on layout,
 *                 not on a mangled message
 */

/** Tamil filler with the conjuncts and above-line marks that stress line-height. */
const FILLER = "தமிழ்மொழியில்நீளமானசொற்றொடர்";

const TAMIL_LENGTH_RATIO = 1.4;

/** Splits on ICU braces so `{count, plural, ...}` is never padded into. */
function padSegment(text: string): string {
  const target = Math.ceil(text.length * TAMIL_LENGTH_RATIO);
  const deficit = target - text.length;
  if (deficit <= 0) return text;
  let filler = "";
  while (filler.length < deficit) {
    filler += FILLER.slice(0, Math.max(1, deficit - filler.length));
  }
  return `${text} ${filler}`;
}

function pseudoString(message: string): string {
  // keep every {...} run verbatim; pad only the literal spans between them
  return message
    .split(/(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})/g)
    .map((part, i) => (i % 2 === 1 ? part : part.trim() ? padSegment(part) : part))
    .join("");
}

type Messages = { [key: string]: string | Messages };

export function makePseudoLocale(source: Messages): Messages {
  const out: Messages = {};
  for (const [key, value] of Object.entries(source)) {
    out[key] = typeof value === "string" ? pseudoString(value) : makePseudoLocale(value);
  }
  return out;
}
