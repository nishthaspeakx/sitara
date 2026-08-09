# packages/schemas — the frozen shared contracts

**One source of truth** for the §34.3 seventeen-module enum, §34.4 error envelope + code taxonomy, §34.6 WebSocket wire protocol, and the §28.2 Today payload. Neutral JSON in `src/` → generated Python (Pydantic v2) in `python/sitara_schemas/` and TypeScript in `typescript/src/index.ts`.

`today.json` is the only source that declares STRUCTURE rather than only a closed set, so the generator carries a small type vocabulary for it: scalars, `X?` (optional), `X[]` (list), and references to an enum or another shape. Keep it that small — anything a richer type system would buy is a thing the wire should not be carrying. Two rules it encodes:
- **The brief enums live here, not in `services/api`.** `sitara_api.daily_guidance.types` imports `Density`, `Tier`, `BriefStatus` and `BriefDegradeReason` from `sitara_schemas.today`, exactly as it already imports `MorningModule`. Both sides of the wire need them and a second declaration is how the two drift.
- **`variant` is deliberately not a field.** §32.1's precedence is a rule over `TodayState`, evaluated once in `apps/web/src/lib/today-variant.ts`. A server that picked the variant would be a second implementation of it.

## Rules
- NEVER edit generated files (`python/sitara_schemas/{__init__,modules,errors,ws_events,today}.py`, `typescript/src/index.ts`) — edit `src/*.json` and regenerate. **Sanctioned exceptions (hand-written, never touched by the generator):**
  - `python/sitara_schemas/facts.py` — §34.2 FactSnapshot contract; rich Pydantic models don't fit the enum/const generator.
  - `python/sitara_schemas/cache_keys.py` — §7.2 cache-key grammar + geohash. Lives here because **both** services build the same strings (astro: global fact subjects; api: Mongo/Redis keys). A second copy would drift, and a drifting key silently repartitions the cache — that is how one city's timings get served to another (§5.3, §30.2).
  Their TS mirrors are deferred until a frontend consumer exists.
- The module enum (17) and control-event set (15) are CLOSED. Adding/removing members = §31.3 change control. The generator asserts the counts.
- New error codes: allowed within the six namespaces (AUTH_/ASTRO_/VOICE_/PAY_/SAFE_/SYS_), PR-reviewed like analytics events (§6.3).
- Generated artifacts are committed; CI regenerates and fails on drift.

## Commands
- Regenerate: `python3 scripts/generate.py` (stdlib only, deterministic)
- Test: `cd python && uv run pytest tests -q` (parity Python↔TS↔JSON)
- TS typecheck: `pnpm --filter @sitara/schemas typecheck`
