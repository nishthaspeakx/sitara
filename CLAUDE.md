# Sitara — build rules (spec = docs/spec/SPEC.md, FROZEN v3.4)
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
