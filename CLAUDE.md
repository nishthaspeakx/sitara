# Sitara — build rules (spec = docs/spec/SPEC.md, FROZEN v3.9)
NEVER change a frozen decision. If a task seems to require it, STOP and say so.

## Non-negotiables (spec §)
- LLM NEVER computes astrology/numerology/dates/timings — engine facts only, cite-or-die (§5.3, §9)
- Facts: logical IDs + full snapshot embedded in every artefact at generation; no facts collection (§34.2)
- Whole-app native language; no silent English fallback ever (§2.4); all strings via i18n keys, ICU format
- Locales: en, hi-Latn (Hinglish), hi first; string keys never hardcoded in components
- Error envelope: {code, message_key, trace_id, retryable}; codes namespaced AUTH_/ASTRO_/VOICE_/PAY_/SAFE_/SYS_ (§34.4)
- Auth: Firebase ID token → POST /auth/session once → httpOnly cookies; Firebase UID=auth id, Mongo _id=product id, auth_identities maps them (§33.2, §34.5)
- Voice notes: original audio stored encrypted 30d default under its OWN CSFLE key class, in Mongo (§33.1 names the mechanism); call audio NEVER stored. Expiry is a JOB that hard-deletes and leaves a `deleted_at` tombstone — never a TTL index, which would delete the tombstone too (§36.2, CC-009). Replay plays the user's ORIGINAL bytes; `playback_policy: synthesised` is refused on a user message at the storage boundary (§25.4)
- messages fields: source_audio_asset_id, tts_audio_asset_id, transcript_status, source_audio_expires_at, source_audio_deleted_at, playback_policy (§6.4)
- WS protocol: binary=16kHz PCM w/ 8-byte header; JSON control events, closed type set (§34.6); schema lives in packages/schemas
- 17 morning modules enum (§7.1/§34.3) — ranking engine emits ONLY these IDs
- Memory: 11 types (§32.4), explicit consent chips, Cohere embed-multilingual-v3 1024d (§32.5)
- Safety: L1–L5 ladder; astrology framing removed at L2+; no fear-selling copy ever (§9, §13)
- Design: tokens only, no hardcoded hex/px (packages/tokens); **49 components** (§24.3 as amended by CC-007 — KundliChart renders in M10, its contract ships now); never call Tara an avatar
- **Tara's likeness is AI-generated and exclusively owned (CC-008)** — NOT a real person, NOT a licensed model. The permanent "Tara · AI guide" disclosure is mandatory; no asset, alt text or copy may describe her as real or licensed, in any locale. Enforced by `apps/web/tests/tara-disclosure.spec.ts`
- Colour usage is measured, not assumed (CC-005): gold and brand-navy are never text, the focus ring carries an outer contour, and `token-lint` verifies every declared contrast pair numerically in BOTH themes
- No dark patterns: no countdowns, no guilt copy, close always visible (§29.2)
- Stories = P1 flag, ring hidden in P0 (§30.6)
- 18+ age gate at signup (§22.4)
- Every in-memory fake or stub must pass the same contract test suite as its real implementation — a fake that accepts what the real system rejects is a defect in the fake. When a new validator or schema constraint lands, the fakes' contract tests must tighten with it. (M5: an in-memory store took string ids where §6.4 requires objectId, so every real write failed validation while the whole suite stayed green.)
- **Browser-side request interception (`page.route` and equivalents) stops a request before the server sees it, so it can never observe middleware, rewrites, redirects, or routing.** Any test asserting a client's handling of an API response must run against a real process the app reaches through its real request path. Intercepts are permitted only for injecting failure modes a real service cannot produce on demand. **A WebSocket has no intercept at all** — the browser-side equivalent is replacing `window.WebSocket`, which is strictly worse: the suite then verifies frame handling over a transport that was never opened, so the handshake, the close, the reconnect and the ordering of frames against the DOM they update are all unobservable. Sockets get a real server (`apps/web/scripts/stub-realtime.mjs`, M8-P10). (CL-013/M8: next-intl's matcher excluded `auth` but not `v1`, so every onboarding step 307'd to `/<locale>/v1/…` and 404'd in a real browser — while the whole flow suite stayed green, because `page.route` had stopped every request before the middleware could redirect it. The suite was verifying that the client handled a response the test invented, and had never once verified the URL that produces it.)
- **Every milestone's acceptance includes an end-to-end run of the real path against live services with real data — the test suite alone never closes a milestone.** A citation gate verifies a sentence stands on a fact; only role-aware fact selection and live-path runs verify it stands on the RIGHT fact. **When a module consumes a fact, it must select by role/entity, never by "first matching shape."** (M6: `moon_nakshatra_note` took the first nakshatra-shaped value in the payload. The engine emits one per graha with the Sun first, so the first live run printed "The Moon sits in Purva Bhadrapada today" citing the SUN's nakshatra — every gate green, the id in the served payload, the name matching the fact it named, and the sentence false. No test could have caught it: the fixtures carried one nakshatra fact. The same run also found that scheduled briefs silently lost their panchang, and that a regenerate cancelled the morning push instead of replacing it.)

## Conventions
- Python 3.12, FastAPI, Pydantic v2, uv, pytest; TS strict, Next.js 15 App Router, next-intl, Zustand+TanStack Query
- Tests first for engine/pipeline code; golden-set tests are release-blocking CI
- Conventional commits; one short-lived branch per milestone (`feat/m5-memory`), merged to main as soon as its shipcheck is green; never commit .env
- **Voice providers sit behind `sitara_api.voice.providers` and are chosen by configuration (§3.2).** Cartesia (Sonic TTS, Ink STT) is the first implementation and M9's default per CC-009; Sarvam stays declared as the Indic STT comparison arm. **§3.2's eight-measure acceptance gate is FINAL and NOT MET** — no bake-off has run, so nothing may describe Cartesia as a shipped primary.
- **A locale is not a language code.** `hi-Latn` IS Hinglish (Latin script), and `locale.split("-")[0]` sends it to `hi`, which fills every Hinglish thread with Devanagari while every accuracy metric stays green. The map is declared data in `voice/providers/base.py`, differs between STT and TTS at exactly that locale, and an unmapped locale DECLINES (§2.4).
- When unsure, read docs/spec/SPEC.md section cited in the task — do not invent
