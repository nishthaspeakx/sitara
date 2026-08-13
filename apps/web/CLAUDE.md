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

### The presence states are §4.3's, from the schema (M8-P10)

`_util.ts` used to declare its own twelve — `warm_neutral`, `smile`, `full_smile`, `reading`, `safety` — none of which are §4.3's names, with `calm_guidance` and `encouragement` missing outright. The API has always emitted §4.3's set. Five of the twelve it can serve had no asset and no alt text here, and the lists differed in ORDER too, so a positional read resolved state 11 (safety-still — the one §29.5 puts in the chat header at L2+) to `reading`. Nothing failed because no screen consumed a served presence state until S18.

`PRESENCE_STATES` now comes from `@sitara/schemas`. Two consequences worth knowing:
- **The asset SLUGS were deliberately not renamed.** They name files built from ~30MB escrow masters (§22.16); renaming a hundred derivatives to tidy a mapping table is a large diff that changes no pixel. `tara-assets.ts` carries the pairing and the reason for each, chosen by looking at every master — a wrong mapping puts a festive portrait on a safety screen.
- **`PaywallPanel` changed image.** §29.5 says "Subscription/paywall: state 1 small", state 1 is `welcome`, and the old list had no state-1 equivalent so it rendered the canonical portrait. That baseline moving is the drift being repaired, not a regression.

### Tara's assets
**Her likeness is AI-generated and exclusively owned (CC-008). She is not a real person and not a licensed human model**, and §25.2's face-model baseline is superseded. Three rules bind anything that touches these files:
- the permanent "Tara · AI guide" disclosure stays wherever her name or face appears;
- no asset name, alt text, caption or copy may describe her as real, photographed, modelled or licensed, in any locale;
- she is still never called an avatar.

`tests/tara-disclosure.spec.ts` enforces all three over every catalog and every component source, so they fail CI rather than depending on review. The guard is negation-aware — "she is NOT a real person" is the correct sentence, not a violation.

`tara-assets.ts` is the only file that knows an asset path. `scripts/build-tara-assets.mjs` produces the responsive WebP + JPEG sets from masters that are **not committed** (~30MB PNGs — escrow material under §22.16). The state→master mapping and the per-master circle crop are art direction encoded as data, both chosen by looking at every master: §29.5 assigns states to surfaces, and a wrong mapping puts a festive portrait on a safety screen. Two states (`concerned_kind`, `safety`) are flagged `approximate` in the manifest — the delivered set has no purpose-made frame for either. Replacements are in generation and land **before M8 ships**, at which point the flags come off.

**Cinemagraphs are deferred post-beta** — a scheduling decision, not a gap. `TARA_MOTION_STATUS` is the record, so no loops in the manifest reads as intent rather than unfinished work. Adding them later is a manifest change, not a component change. Both records are self-checking: `tests/tara-disclosure.spec.ts` fails if a loop appears while the deferral still says deferred, or if the pending-replacement list drifts from the states actually flagged.

## Today (S14, §28.2) — `src/components/today/`

Sixteen variants, three densities, one screen. What is worth knowing before changing it:

- **`src/components/today/` is NOT the component library.** §24.3 is fixed at 49 and `tests/library.spec.ts` scans only `src/components/ui`. Everything here composes library components; nothing here is a new one.
- **§32.1's precedence lives in `src/lib/today-variant.ts`, and only there.** `resolveChrome` returns an already-truncated, already-ordered banner list; `BannerStack` renders it and asks no questions. The API deliberately has no `variant` field for the same reason — two implementations would disagree on exactly the crowded morning the rule exists for (grace + travel + festival + trial). `tests/today-variant.spec.ts` runs with no server.
- **Core-card dominance is counted, not reviewed.** Exactly one `[data-emphasis="core"]` renders, asserted on every one of the 109 baselines. The night takeover and the brief-less variants have zero — §28.2's rule is satisfied by nothing competing, not by something winning.
- **`local_time` is DATA, from the payload.** The night takeover and the sky band never read the browser clock: a screen that did would render a different variant than the brief was generated for, and every baseline would depend on when CI ran.
- **The sky gradient carries no text.** `sky.ts` documents the six contrast failures that established this — `ink-muted` on `gold-soft` is 3.33:1, `gold-soft` is a LIGHT fill in the night theme, and `text-inverse` inverts to navy on a fixed dark sky. Text sits on solid `bg-canvas`, a pair the matrix already verifies in both themes. No colour was added to the frozen palette.
- **`moon_nakshatra_note` belongs to the panchang row**, not the contextual list — §28.2's densities already account for it, so listing it as contextual would spend a max-four slot and print the nakshatra twice. It IS promoted to the core card when nothing better exists (the degraded morning, where the chart half is what failed); `PanchangRow` then shows the strip alone, so it never appears twice.
- **The practical strip is a fixed-width scroller.** Sized to content, the colour chip's sentence is wider than a 390px viewport and pushes the other three off-screen — one row, one chip.
- **`ui.module.${module}` must be written with a BARE identifier.** `i18n-lint` matches the literal template text against `dynamic-keys.json`; `${card.module}` is a template it cannot expand and therefore cannot verify.
- **The `offline` variant is the SCREEN's state, not a payload.** Its baseline needs a failing fetch (`today_unavailable`) over a populated `localStorage` — served over a healthy request it renders an ordinary morning with `offline` in the filename. Seed the cache AFTER the first navigation: `addInitScript` runs on `about:blank` too, and localStorage is per-origin.
- **Never run `pnpm design-qa` beside a foreground `--project=screens` run.** Both bind :3100/:3101; a concurrent pair produced a baseline that passed against one build while the source said another.
- **The three sub-routes are S15–S17** (§29.1): `/today/timings`, `/today/festival`, `/today/brief/[card]/why`. Before they existed the panchang row had to render linkless — a dead end on the home surface is worse than a missing affordance, and the 404 RSC prefetch also hung every `networkidle` wait in the suite. All four surfaces read ONE payload through `loadToday`.
- **The why-route is §30.4's three layers and each must say something different.** Layer 1 is the CLAIM, layer 2 how we know it, layer 3 what the fact holds. Layer 1 was the confidence description at first, which the chip also renders — the sheet then showed one sentence three times and told the reader nothing new.

### The fixtures are recorded, never authored
`tests/__fixtures__/today/` holds 57 payloads produced by the REAL pipeline (`services/api/scripts/record_today_fixtures.py`) and replayed by `scripts/stub-api.mjs` over the real request path. A hand-written brief would be a brief nobody's engine produced, and every baseline taken from it would stay green through any regression in ranking, composition or the §7.1 ladder. `tests/today-fixtures.spec.ts` re-validates each one against the generated schema. **Re-record after any template, ranking or ladder change.**

`src/app/[locale]/dev/today/page.tsx` is the variant switcher — dev-only, driving `/v1/dev/today`, rendering the real `TodayScreen`. **Not `_dev/`:** Next's App Router treats a `_`-prefixed folder as PRIVATE and excludes it from routing entirely (that is what `_launch/` relies on), so the first version 404'd silently while typechecking, linting and building without a word.

## Ask Tara (S18, §25.4) — `src/components/ask/`

§25.4's WhatsApp grammar over the §34.6 socket. What is worth knowing before changing it:

- **`src/components/ask/` is NOT the component library**, same rule as `today/`. §24.3 is fixed at 49 and `tests/library.spec.ts` scans only `src/components/ui`.
- **The thread's behaviour lives in `src/lib/chat-thread.ts` and only there** — a reducer over §34.6 events, no socket and no React. Which bubble a reply belongs to, what a dropped socket does to a message in flight, whether a resumed turn appears once or twice: all of it is `tests/chat-thread.spec.ts`, in the `library` project, with no server.
- **Citation spans are SERVED, never derived here.** `ChatCitation` carries offsets the grounding validator computed. A client that re-derived them would be a second implementation of "what is a claim", disagreeing exactly where it matters. `MessageBubble.contentParts` splits on `[...text]` — **code points, not UTF-16 units** — because an offset off by one in Devanagari reads as a font bug for a week.
- **A single ✓ means delivered-to-Tara.** §25.4 drops read receipts as "meaningless and manipulative for an AI", and `DeliveryState` has three members of which none is "read" — a second tick would have to add one and be noticed.
- **`onClosed` fails the in-flight message on EVERY close, not just the last retry.** It used to fire only when the client gave up reconnecting, which left the bubble on `sending` through five attempts — 36 seconds of a message that looks like it is still going somewhere. The resume buffer holds COMPLETED turns, so a reconnect never rescues a turn that never finished; failed-with-a-retry is the honest state, and a later `resume.offer` heals the bubble if the turn did land. `ask-socket.spec.ts` caught this, which is why that spec drops a REAL socket.
- **The `ws_url` is served by `POST /v1/chat/session`, not built here.** `NEXT_PUBLIC_REALTIME_WS_URL` is gone for the reason `lib/api.ts` records about `NEXT_PUBLIC_API_BASE_URL`: a public build-time origin that must agree with a cookie posture and a deployment topology is a way for the two to disagree silently. It also means the suite points the client at a stub with a server-side env var and no rebuild.
- **L3+ replaces the screen.** The comparison is the schema's `SAFETY_TAKEOVER_FROM_ORDINAL`, declared once so client and server cannot disagree about what L3+ means. `SafetyTakeover` renders no TabBar (a tab bar is four other exits), no portrait (§29.5: institutional calm), and exactly two destinations — §29.1's "exits only to Ask Tara or Help" is structural, not reviewed. `/support/now` (S39) renders the same component.
- **The wallpaper carries no text**, for the six contrast reasons `today/sky.ts` documents. The festival variant §25.4 mentions is deliberately absent until the per-tradition art slots exist — a generic "festival wallpaper" is exactly the generic-Hindu-calendar mistake §25.6 item (4) names.
- **`ui.memory.type.${type}` needs a BARE identifier.** `i18n-lint` matches the literal template text; `${offer.type}` is one it cannot expand. Same rule as `ui.module.${module}`.
- **Voice notes are dark-flagged, not unbuilt.** `VOICE_NOTES_ENABLED` in `src/lib/features.ts`. `VoiceBar` and `VoiceNoteBubble` ship with their states and baselines; what is missing is §33.1's encrypted storage of the ORIGINAL recording, without which §25.4's "replay plays the user's own audio, never a TTS reconstruction" cannot be honoured. A mic button before that storage is a promise the app cannot keep.

### The socket stub is a real server, and that is a stronger rule than CL-013

`scripts/stub-realtime.mjs` is a dependency-free RFC 6455 server. Playwright **cannot** intercept a WebSocket, so the only browser-side alternative would be replacing `window.WebSocket` — and then the suite verifies that the client handles frames the test invented over a transport that was never opened. The handshake, the close event, the reconnect, and the ordering of frames against the DOM they update would all be unobservable. That is CL-013's failure mode with no `page.route` in sight.

`tests/__fixtures__/chat/` holds turns recorded from the REAL §9 pipeline by `services/api/scripts/record_chat_fixtures.py`. Recording matters more here than for Today: a turn carries citation SPANS, and hand-written offsets would draw a plausible underline over words no validator verified — the single defect the S18 baselines exist to catch. **Re-record after any pipeline, presenter or template change.**

## Onboarding — the pre-auth screen (S02)

**§29.1 runs language (S02) BEFORE auth (S03), so S02 has no session** — and every `/v1/onboarding` route is behind one (`CurrentSession`, §33.2/§34.5). S02 called it anyway: every language tap 401'd, `useStepCommit` correctly refused to advance a step it could not persist, and the first screen of onboarding was a dead end in a real browser. Same language or different made no difference.

- **S02 uses `useLocalStepCommit`**, which records the step and advances without a request. There is no `error` on it, because there is no call that can fail — a retry control for an operation never performed is theatre. The choice reaches the server at `POST /auth/session`, which already carries `locale`.
- **`stub-api.mjs` refuses `/v1` without a session, because the real API does.** It used to 200 for anyone, which is exactly why the suite could not see this: the flow tests exercised the click handler, the locale switch and the route against a server that granted onboarding writes to anonymous callers. **A fake that accepts what the real system rejects is a defect in the fake** — the root CLAUDE.md rule, and this is where it was broken.
- **`setupApi` defaults a client to signed-in**; a spec about the pre-auth world opts out with `state: { session_user_id: null }`. Mid-test scenario switches go through `setScenario`, never a raw `/__control/reset` — a hand-rolled one that forgot the session turned every "failed write" test into a 401, which is non-retryable, so `ErrorState` renders no retry control and the test fails for an unrelated reason.
- `tests/onboarding-language.spec.ts` covers S02 with no session, in all three locales, each selecting **its own already-active language** — the case the old suite never had because it always switched languages.

## Storybook + the screenshot-diff gate (§24.8)
`.storybook/preview.tsx` wraps every story in the locale × theme × motion matrix:
- **locale** — en, hi, hi-Latn, plus `ta-Pseudo`, the Tamil-length pseudo-locale (§24.3's longest-string test: ~1.4× English, real Tamil glyphs, ICU placeholders preserved). It is generated in the harness, NOT added to `packages/i18n` — §2.4 admits a locale only through the §12 gate, and a pseudo-catalog next to the real ones is how a fake language ships by accident.
- **theme** — light/reading and night/dusk, via `data-theme`.
- **script** — follows the locale and drives `data-script`, which applies the §24.2 per-script size factor, line-height, tracking and Noto family.
- **motion** — `data-motion="reduced"` forces the §0.12 reduced-motion path.

`tests/screenshots.spec.ts` drives the built Storybook from its own index: for each component's `AllStates` story it captures **4 locales × 2 themes**, plus a reduced-motion baseline for the components that loop. **396 baselines** (49 × 4 × 2, plus 4) live in `tests/__screenshots__/` and are committed — they are the reviewable artefact.

`tests/today-screens.spec.ts` adds **109** for S14 — 16 variants × 3 locales × 2 themes (96), §32.1's own named worst case × 3 × 2 (6), LOW and HIGH density × 3 (6), one reduced-motion night — and `tests/today-routes.spec.ts` **18** more for S15–S17 (3 routes × 3 locales × 2 themes). 127 in total. Density is captured on `normal_morning` only — §28.2 says density changes the ranking engine's output COUNT and never its facts, so the other fifteen would differ by two cards each.

The design-system faces are **vendored** into `public/fonts` by `scripts/vendor-fonts.mjs` and loaded from `src/app/fonts.css` — Fraunces, Inter and Noto per script, subset to what the eight launch languages need (§2.3). Because glyph rasterisation no longer depends on what the machine has installed, `maxDiffPixelRatio` is **0.001**: wide enough for sub-pixel antialiasing, far too narrow to hide a colour, spacing or layout regression. CI fetches nothing — the woff2 files are committed.

## Three output directories, one per mode
`next build` rewrites manifests in its output directory while a running `next dev` reads and rewrites the same files. Sharing one directory corrupts whichever is running, and Next reports it as **"Cannot find the middleware module"** or **`__webpack_modules__ is not a function`** — both name a symptom, not the cause. Deleting the directory does not help: the dev server rebuilds into it and the next build clobbers it again, which is why the failure feels unkillable.

So the modes are disjoint by construction (`scripts/dist-dirs.mjs`):

| mode | directory | notes |
|---|---|---|
| `dev` | `.next-dev` | never deployed, never built into |
| `build` | `.next` | the deployable artefact |
| `build:test` | `.next-test` | carries `NEXT_PUBLIC_AUTH_ADAPTER=fake`, inlined at BUILD time — a separate directory is what stops it becoming the deployed one |

**`next.config.ts` picks by build PHASE, not by an env var.** `next dev` therefore cannot be pointed at a build's directory even by a stray `NEXT_DIST_DIR` in a shell; only a build honours the override, which is how `build:test` and the flow suite's `next start` select the test output.

`tests/dist-dirs.spec.ts` (in the `library` project, no server needed) asserts the three stay distinct, that dev stays non-overridable, that the config still keys off the phase, and that all three are git-ignored. `next-env.d.ts` is **not committed** — every `next` command rewrites it to name whichever directory ran last, and a cold clone typechecks without it.

## Commands
- Dev: `pnpm --filter web dev` (http://localhost:3000/en) · Build: `pnpm --filter web build`
- Lint: `pnpm --filter web lint` · Types: `pnpm --filter web typecheck`
- Storybook: `pnpm --filter web storybook` · `pnpm --filter web build-storybook`
- Library contract + CC-008 disclosure: `pnpm --filter web test`
- Rebuild Tara assets from masters: `node scripts/build-tara-assets.mjs ~/Documents/tara-assets`
- Re-vendor fonts (rarely): `node scripts/vendor-fonts.mjs`
- Screenshots: `pnpm --filter web screenshots` (needs `build-storybook` first) · `screenshots:update` to re-baseline
- Everything, in order: `pnpm design-qa` (from the repo root)
