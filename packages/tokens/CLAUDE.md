# packages/tokens — design tokens (SPEC §24.2, FROZEN values)

Single source `src/tokens.json` (both themes: light/reading + night/dusk per §34.8) → Style Dictionary build → `dist/css/tokens.css` (CSS vars; night overrides via `[data-theme="night"]`) + `dist/tailwind.preset.cjs`.

## Rules
- Token VALUES are frozen (§24.2/§34.8) — changing one is §31.3 change control.
- New night tokens follow the hue-shift rule: same hue as light, +8–12% lightness, −15% saturation, AA-verified.
- Components consume tokens ONLY — `scripts/token-lint.mjs` fails CI on raw hex/px in `apps/*/src` (0px/1px hairlines exempt).
- gold = interactive/sacred/celebratory only (§0.13); caution never red-alarm for astrology; danger = system errors only.
- Light + night themes must define the SAME var names for anything that changes at night (that's how `[data-theme]` override works — see gold).

## Commands
- Build: `pnpm --filter @sitara/tokens build`
- Lint app source: `pnpm token-lint` (root) or `node scripts/token-lint.mjs`
