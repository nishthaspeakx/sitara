# apps/web — Next.js 15 PWA (SPEC §6.2)

App Router with `[locale]` segment routing (next-intl; locale in URL, cookie-pinned). Locales: en, hi-Latn, hi (§2.4). Server Components for content surfaces, client islands for chat/voice/Tara presence.

## Rules
- Strings: i18n keys from `@sitara/i18n` ONLY — a hardcoded user-facing string fails `/i18n` and CI.
- Styling: tokens from `@sitara/tokens` ONLY — raw hex/px fails token-lint. Never call Tara an "avatar"; her likeness is AI-generated and exclusively owned (CC-008), never described as real, photographed or licensed.
- RTL: logical CSS properties from day 1. Accessibility: WCAG 2.2 AA. Touch targets ≥ token touch.target-min.
- Auth calls: httpOnly session cookies (§34.5) — never store Firebase tokens client-side beyond the one-time exchange.
- No dark patterns (§29.2): no countdowns, no guilt copy, close always visible.

## The component library (§24.3) — `src/components/ui`
**49 components, and exactly 49**: 9 foundation + 18 Sitara-specific + 10 structure + 12 feedback (§34.7 as amended by CC-007). `index.ts` carries the manifest; `tests/library.spec.ts` asserts the counts, that every component on disk is declared, that each has an `AllStates` story, and that each is exported. Adding a component without amending the manifest fails CI — that is the mechanical half of "no screen ships a one-off component without design-system review".

Conventions every component follows:
- **Strings are keys, never literals.** A component owns its chrome copy (`ui.close`, `ui.retry`) and takes a `*Key` prop for anything a screen owns. User data (a name, a city, a rendered fact line) comes in as plain props — those are data, not copy.
- **Icons** are Lucide at `ICON_STROKE` 1.5 on a 24px grid (§24.7). Astrology glyphs are custom and Jyotish-lead reviewed.
- **Focus** is the shared `focusRing` (§29.4). Never removed, never restyled per component.
- **Reduced motion** comes free from the token layer — every duration collapses under `prefers-reduced-motion` and under `[data-motion="reduced"]`. Anything that *loops* also needs `motion-reduce:animate-none motion-off:animate-none`.
- **State is never colour alone** (§29.4): a glyph or a label carries it too.

Some rules are enforced by the component's shape rather than by review, and are worth knowing before you work around them:
- `TrustSheet` has **no prop that can carry a fact ID** — §30.4 keeps those internal. It takes sentences the caller already rendered.
- `PriceCard` requires `totalWithTax`, and has no countdown/urgency prop — §30.3's "total incl. tax before the rail" and §29.2's checklist.
- `Toast` holds a module-level single slot: a second open toast renders nothing, so "never stacked >1" cannot be broken by a caller.
- `StoryRing`'s `enabled` defaults to **false**, so a P0 build hides the ring even if a screen forgets the §30.6 flag.
- `BriefCard.module` is typed `MorningModule`, so a card cannot render an id the ranking engine may not emit.
- `KundliChart` ships its **contract and an honest unbuilt state** — CC-007 schedules the diagram for M10. It renders a labelled placeholder plus the house data it would draw, never a wrong chart, so the 49-count is true rather than aspirational. M10 changes the render only.
- `ErrorState` takes a §34.4 envelope; `retryable: false` means no retry control exists at all.

### Tara's assets
**Her likeness is AI-generated and exclusively owned (CC-008). She is not a real person and not a licensed human model**, and §25.2's face-model baseline is superseded. Three rules bind anything that touches these files:
- the permanent "Tara · AI guide" disclosure stays wherever her name or face appears;
- no asset name, alt text, caption or copy may describe her as real, photographed, modelled or licensed, in any locale;
- she is still never called an avatar.

`tests/tara-disclosure.spec.ts` enforces all three over every catalog and every component source, so they fail CI rather than depending on review. The guard is negation-aware — "she is NOT a real person" is the correct sentence, not a violation.

`tara-assets.ts` is the only file that knows an asset path. `scripts/build-tara-assets.mjs` produces the responsive WebP + JPEG sets from masters that are **not committed** (~30MB PNGs — escrow material under §22.16). The state→master mapping and the per-master circle crop are art direction encoded as data, both chosen by looking at every master: §29.5 assigns states to surfaces, and a wrong mapping puts a festive portrait on a safety screen. Two states (`concerned_kind`, `safety`) are flagged `approximate` in the manifest — the delivered set has no purpose-made frame for either. The kit is **stills only**, so no loop is mounted today; adding cinemagraphs later is a manifest change, not a component change.

## Storybook + the screenshot-diff gate (§24.8)
`.storybook/preview.tsx` wraps every story in the locale × theme × motion matrix:
- **locale** — en, hi, hi-Latn, plus `ta-Pseudo`, the Tamil-length pseudo-locale (§24.3's longest-string test: ~1.4× English, real Tamil glyphs, ICU placeholders preserved). It is generated in the harness, NOT added to `packages/i18n` — §2.4 admits a locale only through the §12 gate, and a pseudo-catalog next to the real ones is how a fake language ships by accident.
- **theme** — light/reading and night/dusk, via `data-theme`.
- **script** — follows the locale and drives `data-script`, which applies the §24.2 per-script size factor, line-height, tracking and Noto family.
- **motion** — `data-motion="reduced"` forces the §0.12 reduced-motion path.

`tests/screenshots.spec.ts` drives the built Storybook from its own index: for each component's `AllStates` story it captures **4 locales × 2 themes**, plus a reduced-motion baseline for the components that loop. **396 baselines** (49 × 4 × 2, plus 4) live in `tests/__screenshots__/` and are committed — they are the reviewable artefact.

The design-system faces are **vendored** into `public/fonts` by `scripts/vendor-fonts.mjs` and loaded from `src/app/fonts.css` — Fraunces, Inter and Noto per script, subset to what the eight launch languages need (§2.3). Because glyph rasterisation no longer depends on what the machine has installed, `maxDiffPixelRatio` is **0.001**: wide enough for sub-pixel antialiasing, far too narrow to hide a colour, spacing or layout regression. CI fetches nothing — the woff2 files are committed.

## Commands
- Dev: `pnpm --filter web dev` (http://localhost:3000/en) · Build: `pnpm --filter web build`
- Lint: `pnpm --filter web lint` · Types: `pnpm --filter web typecheck`
- Storybook: `pnpm --filter web storybook` · `pnpm --filter web build-storybook`
- Library contract + CC-008 disclosure: `pnpm --filter web test`
- Rebuild Tara assets from masters: `node scripts/build-tara-assets.mjs ~/Documents/tara-assets`
- Re-vendor fonts (rarely): `node scripts/vendor-fonts.mjs`
- Screenshots: `pnpm --filter web screenshots` (needs `build-storybook` first) · `screenshots:update` to re-baseline
- Everything, in order: `pnpm design-qa` (from the repo root)
