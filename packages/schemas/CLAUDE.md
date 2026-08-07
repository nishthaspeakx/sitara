# packages/schemas — the frozen shared contracts

**One source of truth** for the §34.3 seventeen-module enum, §34.4 error envelope + code taxonomy, and §34.6 WebSocket wire protocol. Neutral JSON in `src/` → generated Python (Pydantic v2) in `python/sitara_schemas/` and TypeScript in `typescript/src/index.ts`.

## Rules
- NEVER edit generated files (`python/sitara_schemas/{__init__,modules,errors,ws_events}.py`, `typescript/src/index.ts`) — edit `src/*.json` and regenerate. **Sanctioned exceptions (hand-written, never touched by the generator):**
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
