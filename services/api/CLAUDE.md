# services/api — FastAPI modular monolith (SPEC §6.3)

Bounded-context modules in one process (auth, users/profiles, localisation, astrology facade, daily-guidance, chat-orchestration, memory, notifications, payments, safety, admin-api, …), typed in-process interfaces, extraction path pre-planned.

## Rules
- Errors: ONLY the §34.4 envelope from `sitara_schemas` — never a custom shape. HTTP status per the §6.3 convention.
- LLM never computes astrology — facts come from the astrology facade over sitara-astro (§5.3).
- All strings via i18n keys; idempotency keys on all mutation endpoints; no secrets/PII in logs (§13).

## Commands
- Run: `uv run uvicorn sitara_api.main:app --port 8001 --reload`
- Test: `uv run pytest -q` · Lint: `uv run ruff check .` · Types: `uv run pyright`
