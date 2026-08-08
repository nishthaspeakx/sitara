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

## db module (M4, §6.4) — invariants that must not regress
- **`db/registry.py` is the only declaration of database shape.** `ensure_schema`, `verify`, `csfle` and the migration runner all read it. Never create a collection or index anywhere else.
- **`tests/db/test_registry_matches_spec.py` parses §6.4 out of `docs/spec/SPEC.md`** and fails on any divergence — retention, shard key, encryption marks, index list. Edit the spec or the registry and the other must follow. Do not weaken this test.
- **Every index beyond §6.4's cell carries a `cite`;** every collection outside the table cites the section that mandates it (§22.5, §25.7, §14-deploy). Undeclared = drift = `verify` exits 1.
- **TTL indexes exist only where §6.4 says "TTL"** (panchang_cache 90d, transit_cache 400d, notifications 180d, story_views 90d per §25.7). Prose retention ("8 years (tax)", "7 years, append-only") is a job's problem — a TTL index there deletes records the spec says to keep, and `verify` fails on it. See §36.2.
- **`transit_cache` uniq is `(date, band, engine_semver)`** — §6.4's `(date, band)` extended per §7.2's key grammar; recorded as §36.1, and a test keeps the extension sourced.
- **CSFLE is explicit, never automatic** (automatic is Atlas/Enterprise-only; dev is Community). Local KMS refuses outside dev/test; deterministic only for the §33.2 contact replicas. `memories.embedding` stays in the clear — you cannot vector-search ciphertext.
- **`voice_sessions` and `call_sessions` structurally reject any audio field** (§13/§33.1). The validator does it, not a convention.
- **Seeds are synthetic only** (§22.12): `@example.invalid` emails, +9199999 phones, `synthetic: true` on every doc; the seeder refuses a non-dev environment or a non-local host.
- Every document carries `created_at`/`updated_at`/`schema_v` — use `db.documents.stamp()`, the validators enforce it.

## Commands (M4)
- Build/repair schema: `uv run python -m sitara_api.db.migrate --phase expand`
- Seed dev data: `uv run python -m sitara_api.db.seed --wipe`
- **Verify against §6.4: `uv run python -m sitara_api.db.verify`** (exit 1 on drift)
