# services/api — FastAPI modular monolith (SPEC §6.3)

Bounded-context modules in one process (auth, users/profiles, localisation, astrology facade, daily-guidance, chat-orchestration, memory, notifications, payments, safety, admin-api, …), typed in-process interfaces, extraction path pre-planned.

## Rules
- Errors: ONLY the §34.4 envelope from `sitara_schemas` — never a custom shape. HTTP status per the §6.3 convention.
- LLM never computes astrology — facts come from the astrology facade over sitara-astro (§5.3).
- All strings via i18n keys; idempotency keys on all mutation endpoints; no secrets/PII in logs (§13).

## panchang module (M3, §5.2 Layer B/D) — invariants that must not regress
- **No majority vote anywhere.** §32.2 replaced §5.2 Layer D's "majority source" with an authority rule. `adjudicate.py` is pure and vote-free; a test parses its AST to keep it that way.
- **Layer A is never outvoted** on deterministic astronomy (boundary instants, sunrise/sunset) — vendor disagreement raises a review flag, never `disputed`. When Layer A cannot answer, §32.2's DivineAPI-primary rule takes over (`FactClass.PANCHANG_ASTRONOMY`).
- **Prokerala is never persisted** — ToS. `PanchangCache.put` raises on it; Layer-A fallbacks are recomputed, not stored. So exactly one provider occupies a panchang row and §6.4's uniq index holds.
- **Cache keys are global** (`sitara_schemas.cache_keys`, §7.2) — a user id in one would fan a person's data across everyone sharing the row.
- **Provider shapes: Prokerala VERIFIED (live sandbox, 2026-01-01), DivineAPI still unverified** — its real endpoint paths are unknown (every guess 404s) and are env-overridable via `DIVINEAPI_PATH_*`. See `tests/panchang/fixtures/README.md`; the skipping provenance test is the honest marker — do not delete it.
- **Prokerala quirks are load-bearing:** krishna-first tithi ids (rotate 15), 0-based nakshatra ids, `index` always 0, offset-bearing `datetime` required, and NO typed muhurat finder (a typed query is declined, never faked).
- CI never calls a vendor: `test_no_live_network.py` blocks DNS + connect for non-loopback.

## Commands
- Run: `uv run uvicorn sitara_api.main:app --port 8001 --reload`
- Test: `uv run pytest -q` · Lint: `uv run ruff check .` · Types: `uv run pyright`
