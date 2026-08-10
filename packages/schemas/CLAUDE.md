# packages/schemas — the frozen shared contracts

**One source of truth** for the §34.3 seventeen-module enum, §34.4 error envelope + code taxonomy, §34.6 WebSocket wire protocol, the §28.2 Today payload, §4.3's twelve presence states, §32.4's eleven memory types and §25.4's chat turn. Neutral JSON in `src/` → generated Python (Pydantic v2) in `python/sitara_schemas/` and TypeScript in `typescript/src/index.ts`.

The generator carries a small type vocabulary for the sources that declare STRUCTURE rather than only a closed set (`today.json`, `chat.json`, `ws-events.json`'s payload shapes): scalars, `X?` (optional), `X[]` (list), and references to an enum or another shape. Keep it that small — anything a richer type system would buy is a thing the wire should not be carrying. Two rules it encodes:
- **The brief enums live here, not in `services/api`.** `sitara_api.daily_guidance.types` imports `Density`, `Tier`, `BriefStatus` and `BriefDegradeReason` from `sitara_schemas.today`, exactly as it already imports `MorningModule`. Both sides of the wire need them and a second declaration is how the two drift.
- **`variant` is deliberately not a field.** §32.1's precedence is a rule over `TodayState`, evaluated once in `apps/web/src/lib/today-variant.ts`. A server that picked the variant would be a second implementation of it.

## Why the closed sets keep moving here (three times now, same story)

A set lands in this package when the two languages turn out to disagree about it — never before, which is the pattern worth naming. §5.4's confidence states drifted first (`verified_limited` vs `verified_limited_birth_data`). Then §4.3's presence states: `sitara_api` numbered the spec exactly while `apps/web` had invented `warm_neutral`/`smile`/`full_smile`/`reading`/`safety` and dropped `calm_guidance` and `encouragement` — five of twelve wrong, and wrong by POSITION, so the server's state 11 (safety-still) was the client's `reading`. Then §32.4's memory types: `packages/i18n` carried a parallel eleven that seven labels disagreed with.

**All three were invisible because no screen consumed the value yet.** That is the shape of the failure, not a coincidence: a closed set with no consumer cannot drift *visibly*, so the drift accumulates until the first screen renders it. The rule that follows — **if both sides of the wire name a set, it belongs here before either side reads it**, not after.

- **The ID is the wire format. `ordinal` is documentation.** §4.3 and §32.4 both number their members and the numbering is genuinely useful (checking this file against the spec line, and §22.9's one "is this L3+?" comparison). It is not what crosses. A positional contract between two lists is precisely how the presence states drifted, and a positional contract *repaired* would drift the same way again.
- **`chat.json` is served identically over HTTP and over the socket.** `POST /v1/chat/turn` and §34.6's `captions.final` carry the same `ChatTurn`. A turn that renders one way over each is two chat screens wearing one name.
- **§34.6's payload typing is deliberately partial.** The text-chat members are typed (S18 sends them); `vad.state`, `barge_in`, `tts.*` and `entitlement.warning` are not, until M9 builds what emits them. `test_only_the_text_chat_payloads_are_typed` keeps the line where it was drawn.
- **`ControlEvent.ack` exists because §34.6's "server acks control events by seq" had nowhere to live.** The member set is closed at fifteen and none of them is an ack, so the acknowledgement rides on the reply. Without the field the sentence is unimplementable — which is why it went unimplemented through M0.

## Rules
- NEVER edit generated files (`python/sitara_schemas/{__init__,modules,errors,ws_events,today,presence,memory_types,chat}.py`, `typescript/src/index.ts`) — edit `src/*.json` and regenerate. **Sanctioned exceptions (hand-written, never touched by the generator):**
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
