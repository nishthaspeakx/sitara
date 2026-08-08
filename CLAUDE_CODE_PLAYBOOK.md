# Sitara Phase 1 — Claude Code Implementation Playbook
**How to build the entire frozen v3.6 specification, end to end, with Claude Code as your primary engineer.**
*Companion to `06-phase1-canonical/Sitara_Phase1_Canonical_Spec_v3.md` (the spec). The spec says WHAT; this playbook says HOW, step by step. Version 1.0 · 30 July 2026.*

---

## Part 0 — Before you write a single line

### 0.1 Accounts & keys you need (get these first; keep keys OUT of prompts)
| Service | What for | When needed |
|---|---|---|
| Anthropic API (Claude) | Tara's brain + Claude Code itself | Day 1 |
| MongoDB Atlas | database (free M0 for dev, M30 later) | Day 1 |
| Firebase project | auth (phone OTP, Apple, Google) | Day 1 |
| AWS account | S3, later ECS/CloudFront (ap-south-1) | Week 1 |
| Swiss Ephemeris licence | astrology engine (CHF ~750, astro.com) | Week 1 |
| DivineAPI (trial → Ananta) | panchang/muhurat/festivals | Week 2 |
| Prokerala (free tier) | cross-check oracle | Week 2 |
| ElevenLabs, Azure Speech, Sarvam, Deepgram | voice bake-off | Week 3 |
| Cohere | memory embeddings | Week 4 |
| Razorpay + Stripe (test mode) | payments | Week 8 |
| Vercel or AWS | frontend hosting | Week 2 |

**Rule:** every key lives in `.env` files (git-ignored) and in a password manager. You NEVER paste a key into a Claude Code prompt — Claude Code reads `.env.example` for shape, never real secrets.

### 0.2 Install Claude Code
```bash
npm install -g @anthropic-ai/claude-code
cd ~/code && claude   # sign in when prompted
```
Baseline settings that matter for this project: use plan mode (Shift+Tab) before every non-trivial task; keep `claude` sessions scoped to ONE package at a time; `/clear` between unrelated tasks so context stays sharp.

### 0.3 The one mental model
Claude Code is a very fast senior engineer who has **never seen your project before every session** — unless you write things down. So this playbook's first real deliverable is memory: `CLAUDE.md` files that carry the frozen decisions into every session automatically. The spec is law; `CLAUDE.md` is the law posted on the wall; your prompts cite section numbers like statutes.

---

## Part 1 — Repository & memory setup (Day 1–2)

### 1.1 Create the build monorepo (separate from the docs repo)
```bash
mkdir sitara-app && cd sitara-app && git init -b main
```
Target structure (Claude Code will scaffold it — Prompt P1 below):
```
sitara-app/
├── CLAUDE.md                  ← root memory (see 1.3)
├── docs/spec/                 ← COPY the canonical spec md + diagrams here
├── apps/
│   ├── web/                   ← Next.js 15 PWA          (CLAUDE.md)
│   └── admin/                 ← Next.js admin           (CLAUDE.md)
├── services/
│   ├── api/                   ← FastAPI monolith        (CLAUDE.md)
│   ├── realtime/              ← FastAPI WebSocket svc   (CLAUDE.md)
│   └── astro/                 ← pyswisseph engine       (CLAUDE.md)
├── packages/
│   ├── schemas/               ← shared Pydantic/TS types, WS protocol, error enum
│   ├── tokens/                ← design tokens (Style Dictionary source)
│   └── i18n/                  ← ICU catalogs, glossary
├── infra/                     ← Terraform + docker-compose.dev.yml
├── golden-set/                ← astrology validation cases (grows to 10K)
└── .claude/
    ├── commands/              ← custom slash commands (see 1.4)
    └── settings.json
```
Copy the spec in: `cp ../sitara-repo/06-phase1-canonical/Sitara_Phase1_Canonical_Spec_v3.md docs/spec/SPEC.md` and the diagrams folder alongside. **The spec travels with the code** — that's what lets every prompt say "per §7.1".

### 1.2 Why this beats "one big prompt"
You cannot paste a 29,000-word spec into every session. Instead: the root `CLAUDE.md` holds the ~40 rules Claude Code must never violate, each pointing at a spec section; each package's `CLAUDE.md` holds its local contract; your task prompts pull in only the sections that matter ("Read docs/spec/SPEC.md §7.1–7.2 then…"). Claude Code reads CLAUDE.md automatically at session start.

### 1.3 The root CLAUDE.md (write this verbatim, then extend)
```markdown
# Sitara — build rules (spec = docs/spec/SPEC.md, FROZEN v3.6)
NEVER change a frozen decision. If a task seems to require it, STOP and say so.

## Non-negotiables (spec §)
- LLM NEVER computes astrology/numerology/dates/timings — engine facts only, cite-or-die (§5.3, §9)
- Facts: logical IDs + full snapshot embedded in every artefact at generation; no facts collection (§34.2)
- Whole-app native language; no silent English fallback ever (§2.4); all strings via i18n keys, ICU format
- Locales: en, hi-Latn (Hinglish), hi first; string keys never hardcoded in components
- Error envelope: {code, message_key, trace_id, retryable}; codes namespaced AUTH_/ASTRO_/VOICE_/PAY_/SAFE_/SYS_ (§34.4)
- Auth: Firebase ID token → POST /auth/session once → httpOnly cookies; Firebase UID=auth id, Mongo _id=product id, auth_identities maps them (§33.2, §34.5)
- Voice notes: original audio stored encrypted 30d default; call audio NEVER stored (§33.1)
- messages fields: source_audio_asset_id, tts_audio_asset_id, transcript_status, source_audio_expires_at, source_audio_deleted_at, playback_policy (§6.4)
- WS protocol: binary=16kHz PCM w/ 8-byte header; JSON control events, closed type set (§34.6); schema lives in packages/schemas
- 17 morning modules enum (§7.1/§34.3) — ranking engine emits ONLY these IDs
- Memory: 11 types (§32.4), explicit consent chips, Cohere embed-multilingual-v3 1024d (§32.5)
- Safety: L1–L5 ladder; astrology framing removed at L2+; no fear-selling copy ever (§9, §13)
- Design: tokens only, no hardcoded hex/px (packages/tokens); 48 components (§24.3); Tara = photographic presence, never call it avatar
- No dark patterns: no countdowns, no guilt copy, close always visible (§29.2)
- Stories = P1 flag, ring hidden in P0 (§30.6)
- 18+ age gate at signup (§22.4)

## Conventions
- Python 3.12, FastAPI, Pydantic v2, uv, pytest; TS strict, Next.js 15 App Router, next-intl, Zustand+TanStack Query
- Tests first for engine/pipeline code; golden-set tests are release-blocking CI
- Conventional commits; one module per PR; never commit .env
- When unsure, read docs/spec/SPEC.md section cited in the task — do not invent
```
Each package gets a short local `CLAUDE.md` (Claude Code writes these in P1) covering its module boundaries, run commands, and test commands.

### 1.4 Custom slash commands (`.claude/commands/*.md`)
Create these five — they turn repeated rituals into one-liners:
- `golden.md` → "Run the golden-set suite (`pytest services/astro/tests/golden -x -q`), report parity %, list every failing case with expected vs actual, and diagnose the first failure down to the calculation step."
- `i18n.md` → "Scan changed files for hardcoded user-facing strings, missing i18n keys, non-ICU plurals, and locale-unsafe date/number formatting. Fix and list what you changed."
- `spec.md` → "Given a section number as $ARGUMENTS, read that section of docs/spec/SPEC.md aloud back to me condensed to its binding rules before we start."
- `review.md` → "Act as an adversarial reviewer of the current diff: correctness, spec compliance (cite §), security (no secrets/PII in logs per §13), i18n, tests. Report findings only."
- `shipcheck.md` → "Run lint, typecheck, tests, i18n scan, and the token-lint; summarise red/green per gate."
Usage in-session: `/golden`, `/i18n`, `/spec 7.1`, `/review`, `/shipcheck`.

### 1.5 CI from day 1 (Claude Code writes it — P1)
GitHub Actions: lint+typecheck (both languages) · pytest (unit) · golden-set job (release-blocking once M2 lands) · i18n lint (fails on hardcoded strings) · token lint (fails on raw hex in components) · Playwright smoke (from M7). Every PR green before merge — including Claude Code's own PRs.

---

## Part 2 — How to run Claude Code on this project (the working method)

**The loop for every task:** (1) `/clear` → (2) `/spec <sections>` → (3) paste the milestone prompt (Part 3) or your own, always with spec citations → (4) Shift+Tab plan mode; read the plan; correct it BEFORE code → (5) let it build with tests → (6) `/review` then `/shipcheck` → (7) you read the diff (yes, actually) → (8) commit with a conventional message → next task.

**Scope discipline:** one bounded module per session (the §6.3 module list is your session map). Long sessions rot — when Claude Code starts forgetting earlier constraints, `/clear` and re-anchor with `/spec`.

**Tests are the contract:** for engine and pipeline code, ask for the tests FIRST ("write the failing tests from §5.5's thresholds, show me, then implement"). The golden set is the single most important asset in the repo — Claude Code maintains the harness; the *expected values* come from Jagannatha Hora/Drik Panchang and your Jyotish lead, never from Claude.

**What Claude Code must never decide:** anything in §26.2 (scope, stack, pricing, timeline), provider selections outside the bake-off gates, safety-policy relaxations, retention/privacy rules. If a session proposes changing one, the root CLAUDE.md tells it to stop — and you should treat that stop as working correctly, not as friction.

**Verification beats trust:** after each milestone, run the thing. `docker compose -f infra/docker-compose.dev.yml up` gives you Mongo+Redis+services locally; the milestone's acceptance line tells you what to click/curl. Claude Code writing "done" is not done; the acceptance check passing is done.

---

## Part 3 — The build, milestone by milestone (14 milestones ≈ 22 weeks)
Each milestone: **Goal → Claude Code prompt (copy-paste) → Acceptance (how YOU verify)**. Prompts assume you ran `/spec` for the cited sections first. Where a milestone is big, run its prompt phases as separate sessions.

### M0 · Scaffold everything (W1) — Prompt P1
**Goal:** the Part-1 monorepo, running locally, CI green on an empty walking skeleton.
**Prompt:** *"Read docs/spec/SPEC.md §6 (architecture) and this repo's CLAUDE.md. Scaffold the monorepo per the structure in CLAUDE_CODE_PLAYBOOK.md Part 1: Next.js 15 App Router app in apps/web with next-intl configured for locales en/hi-Latn/hi and [locale] routing; FastAPI services api/realtime/astro with uv, each with a /healthz route; packages/schemas with the §34.4 error envelope (Python + TS, generated from one source), the §34.6 WebSocket event types, and the §34.3 seventeen-module enum; packages/tokens seeded from §24.2 (both themes) with Style Dictionary → Tailwind config build; infra/docker-compose.dev.yml with mongo, redis and the three services; GitHub Actions per playbook 1.5; per-package CLAUDE.md files; .env.example for every service. Everything must run: docker compose up then curl each /healthz, and pnpm dev serves the web app showing a placeholder in all three locales. Write the README run instructions."*
**Acceptance:** all healthz 200; web app renders `/en`, `/hi-Latn`, `/hi`; CI green.

### M1 · Identity & auth (W1–2) — Prompt P2
**Goal:** §33.2/§34.5 exactly: Firebase sign-in (phone OTP + Google + Apple) → one-time token exchange → httpOnly session; `users` + `auth_identities` collections; session/device management endpoints; 18+ gate.
**Prompt:** *"Read §33.2, §34.5, §22.4, §22.5. Implement the auth module in services/api: POST /auth/session verifying a Firebase ID token via Admin SDK, minting httpOnly access+rotating-refresh cookies; auth_identities mapping per spec; account-link with step-up verification stub; 18+ DOB gate returning ASTRO-free error AUTH_UNDERAGE with in-locale message_key; sessions list + revoke endpoints; OTP throttling per §27 (5 fails → 15-min lock, Redis). Frontend: the S03/S04 onboarding auth screens wired to Firebase client SDK, i18n keys only. Tests: token-exchange happy path, expired/reused refresh, underage rejection, throttle lock, duplicate-provider link conflict returning the §32.12 choose-flow contract."*
**Acceptance:** you can sign up with a test phone number end-to-end locally and see the session cookie; underage DOB blocks with a translated message.

### M2 · The astrology engine — crown jewel (W2–5) — Prompts P3a/b/c
**Goal:** services/astro per §5: pyswisseph charts (Lahiri), nakshatra+pada, vimshottari dasha, transits; own geocode+historical-tz resolver; typed fact snapshots (§34.2); golden-set harness as release-blocking CI.
**P3a (facts & charts):** *"Read §5.2, §5.5, §34.2. In services/astro implement: birth-chart computation with pyswisseph (Lahiri ayanamsa; whole-sign houses presented, bhava computed), planetary longitudes, nakshatra+pada, vimshottari maha/antar/pratyantar dasha, current gochar transits. Output = typed FactSnapshot objects {fact_id, kind, value, precision, method, valid_from, valid_to, engine_semver, data_revision} per §34.2 — write the Pydantic models in packages/schemas first and show me. Timezone: resolve historical offsets via IANA tzdb from stored place+datetime; NEVER trust an external astrology API for tz. Tests first: derive 25 seed cases from docs/spec §5.5's edge list (DST transitions, midnight births, leap years, half-hour zones, Lord Howe, Nepal) with placeholder expected values marked NEEDS_VERIFICATION for my Jyotish reviewer."*
**P3b (golden harness):** *"Build golden-set/ as a versioned YAML case format {input: birth data, expected: facts, source: JHora|Drik|Jyotish-lead, status: verified|pending} with a pytest runner that reports parity % per §5.5 thresholds (positions ≤1 arc-min, boundaries ≤2 min, dasha ≤1 day) and a CI job that FAILS the build under 99.9% parity on verified cases. Add a CLI to import cases from CSV so the Jyotish lead can supply batches."*
**P3c (numerology):** *"§5, §22.10, §32.4-adjacent: Chaldean-primary numerology on the confirmed Latin transliteration (ISO 15919 helper with confirm-flow contract), Pythagorean secondary; 500-case hand-check harness; moolank/bhagyank fact snapshots."*
**Acceptance:** golden runner prints parity; your Jyotish reviewer verifies the first 100 cases against Jagannatha Hora and flips them to verified; CI blocks on regressions. **This gate (W8, ≥99.9% on the verified set) is the spec's first tranche-evidence gate — do not proceed to guidance generation until it's green.**

### M3 · Panchang providers + comparison engine (W3–5) — Prompt P4
**Prompt:** *"Read §5.2 Layer B/D, §32.2, §7.2. Build the PanchangProvider interface with DivineAPI primary and Prokerala cross-check adapters (circuit breakers, §34.4 errors, keys from env); panchang_cache and transit_cache collections with the §7.2 key schema (global, geohash4+tradition — never per-user); the nightly comparison job per §32.2: Layer A authoritative for chart facts, DivineAPI primary for panchang, disagreements beyond tolerance flag `disputed` + queue admin adjudication; muhurat/choghadiya/rahu-kaal endpoints accepting explicit place (§30.2). Contract tests against recorded fixtures (record real responses once with my trial keys, then replay)."*
**Acceptance:** `curl /panchang?date=…&city=Mumbai` returns cached facts; kill the DivineAPI key and watch the Prokerala fallback + honest degradation.

### M4 · Data layer complete (W4–5) — Prompt P5
**Prompt:** *"Read §6.4 in full. Create every collection with indexes, TTLs and validators exactly per the table (users, auth_identities, profiles, birth_details, family_members, charts, caches, numerology_profiles, conversations, messages with the six §33.1 audio fields, memories, daily_briefings, guidance_logs, night_reflections, goals, notifications, voice_sessions/call_sessions, subscriptions, payments, consents, safety_events, audit_logs, localized_content, pronunciation_dictionaries, feature_flags, stories+story_views dark); CSFLE on the marked fields (local KMS provider for dev, AWS KMS interface for prod); migration runner (expand→migrate→contract per §14-deploy); seed script with synthetic personas only (§22.12 — no real PII ever in dev)."*
**Acceptance:** `python -m api.db.verify` prints every collection/index matching §6.4; seeds load; CSFLE round-trips a birth record.

### M5 · Conversation pipeline (W5–8) — Prompts P6a/b
**P6a (pipeline core):** *"Read §9, §5.3, §34.4. Implement the mandatory turn pipeline in services/api chat-orchestration: language/script detection → L1 safety pre-check (start rule-based + Claude classifier, thresholds in config) → intent routing (structured output) → required-data/confidence state (§5.4 five states) → parallel: memory retrieval (stub) + astrology fact tool-calls → fact validation → Claude generation (persona + locale style guide as cached system prefix; temperature 0.2 guidance / 0.7 small talk) → grounding validator (every astrological claim cites a fact_id present in the payload — REJECT and regenerate once) → language-quality validator (locale, script, glossary lint) → safety post-check (fear-selling lint corpus in config) → store message with fact snapshots → memory-chip suggestion stub. Langfuse-compatible tracing hooks; token budget with rolling summary. Tests: a fabricated-transit response must be caught by the grounding validator (write that test FIRST with a mocked LLM)."*
**P6b (memory):** *"Read §32.4, §32.5, §8-memory diagram. Implement the 11-type memory service: consent-chip contract, Cohere embed-multilingual-v3 (1024d) behind the model-abstraction layer with the OpenAI fallback wired, Atlas Vector Search index (Mongo dev fallback: exact search), visibility gates per type, decay job, vault CRUD with hard-delete + embedding removal, §30.5 scoped-deletion semantics. Cross-lingual retrieval test: store in Hindi, retrieve from an English query, ≥0.85 recall on the 50-pair starter set."*
**Acceptance:** chat with Tara locally in three locales; ask her a chart question and open the payload — every claim carries a fact snapshot; try to trick her into inventing a muhurat and watch the validator reject it.

### M6 · Morning brief pipeline (W6–9) — Prompt P7
**Prompt:** *"Read §7.1, §34.3, §23. Implement Celery+Beat morning generation: 15-min tick selecting users in the 90–30-min lead window (local brief_time, §32.13 one-per-local-date idempotency incl. locale in the key per §32.7); global panchang pre-jobs; the ranking engine choosing from EXACTLY the 17-module enum with density modes (§28.2) and priority queues paying>trial>dormant-on-open; template composition + batched LLM polish with prompt caching; grounding gate; §7.1 degradation to verified-core-cards; notification enqueue for exact local time with §23.4 expiry/collapse; location-change and locale-change targeted regeneration triggers. Load-simulate 5,000 synthetic IST users and report the wave spread histogram."*
**Acceptance:** set your own brief_time two minutes ahead, watch the worker generate and the (local) push fire; change your city to London and see the targeted regenerate.

### M7 · Frontend foundations (W4–7, parallel track) — Prompt P8
**Prompt:** *"Read §24.2–24.3, §29.3–29.4, §0.12–0.13. Build packages/tokens completely (both themes incl. the §34.8 night set, per-script type tokens) and the 48-component library in apps/web with Storybook: every §24.3 component, all states, token-only styling (add the CI token-lint), locale test stories using Tamil-length strings, dark theme, reduced-motion variants; TrustSheet per §30.4 three layers; ConfidenceChip five treatments per §34.7; TaraPresence host with poster fallback (use placeholder portraits until the shoot). Playwright screenshot-diff baseline per component per locale."*
**Acceptance:** Storybook shows 48 components × states; token-lint fails a PR with a hardcoded hex (test it on purpose).

### M8 · Onboarding + Today + chat screens (W6–10) — Prompts P9a/b/c
Three sessions: **P9a** onboarding stack S01–S13 (§24.4, §28.1 route map, §30.1 value-first permissions, §0.17 first-three-minutes ceremony, launch animation per §0.11 with the five analytics paths); **P9b** Today with all 16 variants × 3 densities and the §32.1 banner stacking rule (build a dev "variant switcher" page so you can eyeball every state); **P9c** WhatsApp-familiar chat per §25.4 wired to the M5 pipeline via the realtime service (§34.6 protocol from packages/schemas), voice notes UI dark-flagged until M9.
**Acceptance:** full journey locally: land → language → sign up → birth details → first reading wow-moment → next morning's brief on Today → chat with Tara — in Hinglish end to end.

### M9 · Voice notes + live call (W10–13) — Prompts P10a/b
**P10a (voice notes):** *"Read §33.1, §25.4, §28.3. Implement hold-to-record voice notes: client capture → WS upload → STT adapter (Sarvam primary, Deepgram EN; recorded-fixture tests) → transcript message + encrypted original audio to S3 (30d lifecycle, per-note delete, delete-after-transcription setting, §33.1 field model); WhatsApp-style bubbles playing ORIGINAL audio; Tara TTS voice-note replies with transcript toggle."*
**P10b (live call):** *"Read §25.3, §34.6, §33.5, §32.9/32.11/32.14. Implement /ask/call: full §34.6 protocol on services/realtime (VAD ducking barge-in, heartbeats, resume-offer, handoff.to_text with context), call screen per the §25.3 reference layout (portrait placeholder, timer, mute/end/speaker, plan chip reading entitlements, live captions ON first call), minute metering + 5/2-min warnings, degrade ladder chaos test (kill TTS mid-call → clean text handoff). Instrument every §33.5 gate metric."*
**Acceptance:** you talk to Tara in a real call locally; pull your network cable mid-sentence and land softly in text with context intact. The §33.5 gate dashboard exists from day one.

### M10 · Night, Journal, Memory vault, Family (W10–12) — Prompt P11
Night reflection with dusk takeover (§28.2 night, §24.4 S24), Journal one-home IA (§30.5), Memory Vault with consent ledger, Family profiles with attestation + "in memory of" (§27), Travel Mode (§30.2). **Acceptance:** the full daily emotional arc works: morning → chat → night close, and everything lands in exactly one home.

### M11 · Money, notifications, admin (W10–14) — Prompts P12a/b/c
**P12a payments:** §30.3 complete in test mode — Razorpay (UPI Autopay mandates) + Stripe, S30/S31/S34 screens, §22.13 dunning states, gifting incl. already-subscribed credit conversion, billing-region migration rules, webhook reconciliation + idempotency (test double-webhook on purpose). **P12b notifications:** full §23 system — classes, 6-trigger catalogue, fallback ladder, §23.5 preference matrix, quiet hours with the §32.6 brief exception, dead-token lifecycle; local email via Mailpit, WhatsApp behind an adapter fixture until BSP approval. **P12c admin:** apps/admin per §12 with §32.3 RBAC seed, locale gate physically requiring the checklist record, comparison-engine adjudication queue, safety queue, stories module (dark), audit logging on every sensitive action.
**Acceptance:** a full test purchase → receipt → simulated failed renewal → grace banner → recovery; the locale flag refuses to enable Gujarati without a signed checklist.

### M12 · Safety hardening + localisation pipeline (W12–15) — Prompt P13
Red-team harness (fear-selling, injection per §22.8, crisis incl. code-switched — run as CI corpus with zero-critical gate); L2–L5 behaviours incl. mid-call §27 rule; Trust-Sheet correction loops (§30.4 "this looks wrong" → adjudication ticket); i18n extraction of ALL strings to packages/i18n with the TMS sync script; per-locale screenshot-diff across the 46-entry matrix. **Acceptance:** the red-team suite runs in CI; a deliberately-planted fear sentence fails the build; the string-coverage report shows 100% keys for en/hi-Latn/hi.

### M13 · Production infra + performance (W14–17) — Prompt P14
Terraform for the §6 production stack (ECS Fargate, Atlas M30 ap-south-1, ElastiCache, S3+CloudFront, Secrets Manager); §14-deploy CI/CD with canary + §8 SLO alarms; k6 load tests (Stage-1×2 + morning-burst sim); PWA polish (offline shell, install flows per §30.1, TWA wrapper); WCAG 2.2 axe pass + manual focus walk; pen-test prep checklist. **Acceptance:** staging on real infra survives the burst test inside SLOs; Lighthouse PWA + a11y green.

### M14 · Beta ops (W17+) — Prompt P15
Feature-flag cohorts, §31.1 round-3 instrumentation, PostHog funnels (onboarding, trial→paid, call adoption), §18 per-language dashboards, incident runbooks, status page. **Acceptance:** the beta-exit gate metrics (§21) are all visible on one dashboard before the first beta user arrives.

---

## Part 4 — Guardrails, gotchas & the honest notes

**Claude Code's PRs get reviewed like a human's.** Use `/review` in a FRESH session (fresh context = honest reviewer), then read the diff yourself. The two places you personally must understand every line: the astrology engine and anything touching payments or consent.

**The golden set is human-verified, full stop.** Claude Code builds the harness and can propose cases, but expected values enter as `verified` only via your Jyotish lead's sign-off CLI. An LLM verifying an LLM's ephemeris maths is the exact failure §5 exists to prevent.

**Sequence reality:** M0–M6 are one track (backend-heavy), M7–M8 a parallel frontend track — this mirrors the spec's team plan. Solo with Claude Code, run them interleaved and expect the §33.4 P0-Core checkpoint (EN+Hinglish daily loop, text, payments, safety) around W12 — that's the moment you put it in five real people's hands. Claude Code compresses engineering, **not** the human-gated paths: the Jyotish verification, the voice bake-off panels, the photoshoot, translations, Meta/BSP approvals and the pen test keep their calendar time. Guard the §26.2 baseline accordingly.

**Cost note:** expect the Claude Code + Claude API dev spend to live inside the spec's "AI + voice usage (build + beta)" line (₹8L baseline) — track it weekly in the cost dashboard from M0, not at the end.

**When Claude Code and the spec disagree, the spec wins — and when the spec and reality disagree, change control wins:** file a §26.1 decision-log entry in the docs repo, bump the version, then build. That discipline is what six audit rounds bought you; don't spend it in week 3.

*End of playbook. Pair it with the spec, start at Part 0, and the first "Namaste, main Tara hoon" is about twelve weeks of honest work away.*
