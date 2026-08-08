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

## chat_orchestration module (M5, §9) — invariants that must not regress
- **The stage order in `pipeline.py` IS §9's mandatory pipeline.** `Stage` names every step; `test_stage_order_is_the_spec_order` reads the trace and asserts the sequence. Adding a stage means editing the spec first.
- **Cite-or-die is mechanical, not prompted.** `grounding.py` rejects (a) an uncited astrological claim, (b) a `[[fact:…]]` id absent from the served payload, (c) a number not in the cited snapshot. The claim lexicon is derived from the `sitara_schemas` enums plus `policy/claim_terms.json`; **strong vs weak matters** — a weak term needs a number beside it, or Tara could never say "I don't have your birth chart yet" without failing her own validator.
- **Exactly ONE corrective regeneration**, then the safe fallback line + `safety_events` review row (§9, §2.4 rule 8). `ChatSettings` raises if anyone sets it to anything but 1.
- **L4 never reaches the model** (§22.9) — templated, instant, machine-delivered, queued for human oversight. L2+ removes astrology *at routing*, so no fact tool is even called.
- **The §22.8 allowlist is applied in code** after the router speaks (`TOOL_ALLOWLIST`), never by asking the model nicely.
- **A tool that cannot answer declines** (`FactToolUnavailable`) and the turn goes to a template. Granted tools returning nothing → `chat.data.cannot_calculate`; handing the model an empty payload plus a chart question is the shape of a fabrication.
- **The trace records shapes, not content** (§13): `TurnTrace` hashes text unless `trace_capture_content`, which `build_tracer` refuses outside dev/test. Langfuse-shaped events go through a `TraceSink`.
- **System blocks are the cached prefix** (§9): persona → citation contract → locale style guide, most-stable first. Nothing per-turn above the breakpoint, or every user's cache dies every turn. Bump `prompts.PROMPT_VERSION` on any edit.
- **A blank `ANTHROPIC_API_KEY` is "provider down", not a boot failure** — `build_pipeline` returns None and `/v1/chat/turn` serves the §34.4 `SYS_UNAVAILABLE` envelope.
- **Identifiers become ObjectIds at the store boundary, nowhere else.** §6.4 types `messages.conversation_id`, `guidance_logs.user_id` and `guidance_logs.message_id` as `objectId`; the pipeline carries §33.2's product identity as a string. `store.to_object_id` is the single conversion and refuses a non-`_id` loudly. **`tests/chat/test_store_mongo.py` writes through the real §6.4 validators** — it exists because the in-memory fake once accepted strings the real collection rejected, so the whole suite was green while every real write failed. Do not delete it, and keep `InMemoryMessageStore` minting real ObjectIds.
- **An outage is not a safety event.** A provider failure serves the fallback line and does NOT queue a human (§8 degradation); only a validator double-failure or an L4 writes `safety_events` (§22.9's 24h SLA). `safety_events.classifier_scores` carries the real L1 labels plus the trigger, CSFLE-encrypted under the `safety` key class.
- **The cache breakpoint goes after the last STABLE system block**, never simply on the last one — `LLMRequest.cacheable_prefix_len` carries it. Below the breakpoint sits the per-turn safety register; inside it, every L2+ turn would be a cache write instead of a read.
- **The service renders §9's safety and decline strings itself**, so `packages/i18n/messages` ships in the image and `localisation.verify_catalogs` refuses to boot without them. Discovering a missing catalog when an L4 turn needs the crisis line is the one failure mode worth a startup crash.
- **The claim lexicon's word boundaries are load-bearing** in both validators: "Tara" inside "tarah" (everyday Hinglish) once failed ordinary replies and burned the single regeneration.
- **Open §31.3 item — CLOSED as §37 (CC-004):** §9's sampling control is capability-relative. The pipeline declares 0.2/0.7; `llm.py` applies them where the pinned model accepts them and records `temperature_declared` + a trace note where it cannot. Do not quietly delete the declaration.
- **Release gates:** `uv run python -m sitara_api.release_gates` reports the human-closed §31.7 gates (helpline table, both safety corpora). `/shipcheck` runs it; three are open and block closed beta.

## memory module (M5-P6b, §32.4/§32.5/§30.5) — invariants that must not regress
- **`memory/taxonomy.py` is the ONE home for the 11 types**, their consent rules, gates and decay policy. `chat_orchestration.types` re-exports; it never redeclares. `tests/memory/test_taxonomy.py` parses §32.4 out of `docs/spec/SPEC.md` and fails on drift — same discipline as `test_registry_matches_spec.py`.
- **No chip, no memory.** `MemoryStore.create` takes a `ConsentRecord` in its signature — there is no path that stores content without one — and refuses a type 7–9 memory whose wording was not re-confirmed (§32.4). Symptoms/diagnoses are declined at classification, in code as well as in the model.
- **Delete is hard delete, embedding included** (diagram 8). No tombstone. §30.5's scoped effects are separate verbs, not flags: journal-entry deletion has a checkbox (`delete_memories`), conversation deletion marks `source_state: removed` and the memory SURVIVES — consent did not expire with the thread.
- **Decay never deletes.** §32.4 retains "until user deletes". Below `RETRIEVAL_FLOOR` a memory goes quiet and stays in the vault; the nightly job writes scores only.
- **Retrieval recomputes decay from the clock**, never trusting the stored `decay_score` — the job writes that value and may be hours stale. `updated_at` is the reinforcement stamp: an edited memory is young again.
- **The exact-search fallback is not a toy** — same cosine, same vectors, same ranking as Atlas, so a query ranks identically on a laptop. It is capped at 500 rows and LOGS when it truncates.
- **Vectors from two models never mix** (§32.5): `embedding_model` is stamped on every row and both search paths skip foreign spaces. The re-embedding batch job is what reconciles them.
- **§32.5's recall gate needs REAL vectors.** The deterministic embedder hashes tokens and is not cross-lingual; `test_crosslingual.py` demonstrates it cannot pass, then skips unless `tests/memory/crosslingual/vectors.json` exists. Record with `COHERE_API_KEY=... uv run python -m tests.memory.crosslingual.record`. Never soften the gate to make it green.
- **OpenAI fallback must send `dimensions: 1024`** — text-embedding-3-large is natively 3072-d and §6.4's index is 1024-d. `Embedding.__post_init__` refuses any other width.
- **`make_mongo` sets `tz_aware=True`** — BSON stores UTC but the default codec returns NAIVE datetimes, and mixing them raises TypeError mid-arithmetic. Decay hit this; panchang's cache had a local workaround for the same hazard.
- **`populate_by_name=True` on every settings class carrying a `validation_alias`** — an alias REPLACES the field name, so `Settings(cohere_api_key=...)` silently yields None otherwise. It did, in `ChatSettings`, for a whole milestone.

## auth age gate (§22.4 / §37.2) — invariants that must not regress
- **The gate never runs in UTC, and never in a zone the CALLER chose.** The zone set is corroborated from the E.164 country of the Firebase-verified phone (× request-IP country when available); a declared zone is honoured only if it is already in that set. Age is evaluated in the **westernmost** member — the smallest age the evidence permits.
- **It fails closed.** No corroborated set → retryable `SYS_UNAVAILABLE` (`errors.auth.zone_unverified`), never a guess. **This blocks sign-ups with no phone number (Google) today** — tracked as `auth.zone_corroboration_coverage`.
- **No audit, no decision.** The audit write PRECEDES the outcome; a failed write returns retryable SYS_UNAVAILABLE rather than an unaudited admission *or* refusal.
- **Never persist anything derived from a date of birth.** `audit_logs` has no §6.4 encryption marks and retains 7 years. The row holds outcome + zone set + provenance. `db.redact_age_targets` rewrites legacy `age=` rows in place — it never deletes them (append-only).
- **`audit_logs` is STRICT** (`additionalProperties: false`). A strict collection must declare `_id` explicitly or it rejects every write with an error naming no field.

## text/script invariants (CL-003)
- **Never `\b` on text that can contain Devanagari** — vowel signs and the virama are combining marks Python excludes from `\w`, so `\bवक्री\b` matches nothing. Use `sitara_api.text.bounded`/`alternation`. The danda `।` must stay OUTSIDE the word class or terms at a sentence's end never match.
- **`tests/chat/test_script_boundaries.py` asserts no safety pattern is inert** — 120 patterns, parametrised. It guards itself with a test that `is_inert` still flags `\bवक्री\b`. An empty probe is a FINDING, not a pass.
- **Every §-citation must resolve** — `tests/spec/test_citations_resolve.py` fails on a dangling one. §10's journey stages are cited `§10-6`, with a hyphen.

## Commands (M5-P6b)
- Nightly decay: `uv run python -m sitara_api.memory.decay --dry-run` (§32.4 consolidation)
- Record the §32.5 recall vectors: `COHERE_API_KEY=... uv run python -m tests.memory.crosslingual.record`
- Redact legacy age targets (§13): `uv run python -m sitara_api.db.redact_age_targets --dry-run`

## Commands (M4)
- Build/repair schema: `uv run python -m sitara_api.db.migrate --phase expand`
- Seed dev data: `uv run python -m sitara_api.db.seed --wipe`
- **Verify against §6.4: `uv run python -m sitara_api.db.verify`** (exit 1 on drift)
