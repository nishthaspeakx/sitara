# packages/tokens — design tokens (SPEC §24.2 / §29.4 / §34.8, FROZEN values)

Single source `src/tokens.json` → Style Dictionary → `dist/css/tokens.css` (CSS vars) + `dist/tailwind.preset.cjs`.

Layers in the CSS output:
- `:root` — light/reading theme + every non-colour token
- `[data-theme="night"]` — the complete §34.8 dusk set
- `[data-script="devanagari|gujarati|gurmukhi|tamil|telugu"]` (`:root` = latin) — rebinds the active font family, size factor, line-height and tracking. Every `text-*` utility is script-tuned by construction: the size scale is `calc(<rem> * var(--font-script-size-factor))` and each Tailwind fontSize entry carries the script line-height and letter-spacing.
- `@media (prefers-reduced-motion: reduce)` and `[data-motion="reduced"]` — collapse every motion duration to 0.01ms, so a token-only component gets its §0.12 reduced-motion equivalent for free.

## Rules
- Primitive colour VALUES are frozen (§24.2/§34.8) — changing one is §31.3 change control.
- Semantic tokens (§29.4) alias a primitive wherever an alias exists. Where §29.4 names a token the frozen palette has no primitive for, the value is derived on the source primitive's hue and recorded in `src/contrast-matrix.json → derived`. Nothing enters the palette unexplained.
- Components consume tokens ONLY — `scripts/token-lint.mjs` fails CI on raw hex/px in `apps/*/src` (0px/1px hairlines exempt).
- gold = interactive/sacred/celebratory only (§0.13); caution never red-alarm for astrology; danger = system errors only.
- Light + night must define the SAME var names for anything that changes at night (that's how `[data-theme]` override works).

## Fill tokens are not text tokens
A utility class is theme-agnostic, so a token that fails 4.5:1 in *either* theme is banned as text in *both*. `restrictedAsText` in `src/contrast-matrix.json` lists each one with its reason and its replacement; the lint enforces it over `text-` / `placeholder-` / `caret-`. The paired `*-text` tokens (`feedback-caution-text`, `astro-auspicious-text`, `feedback-danger-text`, …) exist for copy.

Two consequences worth knowing before you reach for them:
- **gold is never text** (2.42:1 on cream). An interactive label is `text-ink-primary underline decoration-gold` — the gold underline carries the §0.13 "this is tappable" signal without carrying the legibility. `decoration-*` is deliberately not linted.
- **brand-navy is never text.** §34.8 defines no night override for it, so navy copy is ~1.1:1 on the night canvas. Use `ink-primary`, or `feedback-info` when you want the accent (it is theme-aware).
- The **focus ring** is gold + a `focus-ring-outer` contour. Gold alone is 2.42:1 on cream and cannot satisfy WCAG 2.2's focus-indicator contrast; the outer contour carries it at 12.93:1 without touching the frozen gold value. §29.4's "2px gold ring + 2px offset" is unchanged.

## The hue-shift audit, honestly
§24.2's rule is "same hue, +8–12% lightness, −15% saturation, AA-verified". The lint enforces **hue preservation against the declared source primitive** and **AA** (hard, via `pairs`); it *reports* lightness/saturation deltas rather than failing on them. Two reasons, both recorded in `src/contrast-matrix.json`:
1. The frozen palette itself does not preserve hue across themes — light `line` is h47 (warm cream), night `line` is h233 (blue) — so a night token derived from its night parent legitimately shares no hue with its light counterpart.
2. The rule's own closing clause is "AA-verified against night surfaces", and a text token on a `#12162E` canvas cannot be legible at light-lightness +10%. Where the two halves conflict, AA wins.

Run `node scripts/token-lint.mjs --explain` to print the full derivation ledger.

## Commands
- Build: `pnpm --filter @sitara/tokens build`
- Lint (all three gates): `pnpm token-lint` (root) · `--source-only` · `--contrast-only` · `--explain`
