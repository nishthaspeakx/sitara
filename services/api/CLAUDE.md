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
- **Cite-or-die is mechanical, not prompted.** `grounding.py` rejects (a) an uncited astrological claim, (b) a `[[fact:…]]` id absent from the served payload, (c) a number not in the cited snapshot, and (d) **a sentence about a different BODY from the fact it cites** (M8-P10). (d) is the one (a)–(c) cannot see and the one that has actually shipped: "Venus is in your 10th house" citing Saturn's 10th-house fact passes every numeric test, because the 10 is in the fact verbatim. CL-009 is that shape with the Moon and the Sun. It compares **like with like** — grahas against grahas, nakshatras against nakshatras — because a panchang nakshatra fact holds no graha at all and comparing across classes failed `moon_nakshatra_note` for being right. Locale surfaces come from `terms.*` in the i18n catalogs (§14-reviewed); `policy/claim_terms.json`'s `celestial` block, now keyed by canonical body, carries only the synonyms the catalog lacks (बृहस्पति beside गुरु). **That block feeds two other readers as a flat set** — restructuring it once handed them the dict's keys and every Devanagari graha name silently left the claim net. The claim lexicon is derived from the `sitara_schemas` enums plus `policy/claim_terms.json`; **strong vs weak matters** — a weak term needs a number beside it, or Tara could never say "I don't have your birth chart yet" without failing her own validator.
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
- **`memory/taxonomy.py` owns the 11 types' RULES** — consent, visibility gates, decay policy. `chat_orchestration.types` re-exports; it never redeclares. `tests/memory/test_taxonomy.py` parses §32.4 out of `docs/spec/SPEC.md` and fails on drift — same discipline as `test_registry_matches_spec.py`. **The IDS moved to `sitara_schemas.memory_types` in M8-P10**, because S18's memory chip made them a wire format: `packages/i18n` had meanwhile grown a parallel eleven (`life_fact`, `concern`, `belief_practice`, `conversation_thread`…) that seven labels disagreed with, and §32.4 ends "Vault filters use exactly these 11 labels". Rules here, ids there, one declaration each.
- **`PresenceState` is `sitara_schemas.presence`, and it is a StrEnum.** It was an IntEnum here; `apps/web` held a differently-named, differently-ORDERED twelve, so a positional read of a served state resolved this module's `SAFETY_STILL` (11) — §29.5's chat-header state at L2+ — to the client's `reading`. `TurnResponse.presence_state` is now the ID, not the ordinal.
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

## daily_guidance module (M6, §7.1) — invariants that must not regress
- **`windows.py` is pure and clock-driven.** No database, no Celery, no network — a DST boundary at the date line is a hard case to reason about and a trivial one to reproduce. `tests/daily_guidance/test_windows.py` IS §23.9's timezone matrix for the selection half.
- **The lead window is a SCHEDULE, not a filter** (CL-008 §1). A 60-minute window sampled every 15 minutes contains each user for FOUR ticks; the `lead_minutes` hash picks the ONE tick they fire on. `blake2b`, never `hash()` — the built-in is salted per process, so every worker would draw a different slot and the smoothing would become noise.
- **`local_instant` returns UTC, always.** PEP 495 makes an aware datetime that is AMBIGUOUS in its zone compare unequal to its own instant elsewhere while comparing neither less nor greater — trichotomy fails and every `==`, `in`, dict key and sort over it is quietly wrong twice a year. The test demonstrates the hazard before asserting the guard.
- **The ranking engine emits ONLY `MorningModule`** (§34.3) and only where the evidence is in hand (§5.3). `MODULE_FACT_KINDS` declares what each of the seventeen may stand on; two import-time asserts keep every module reachable from exactly one density bucket and gated by a declared requirement. **Density caps the COUNT, never the facts** (§28.2).
- **Composition happens before the model, from facts alone.** That is what makes §7.1's degrade cheap: falling back to composed text can never ship an uncited claim, because composed text is where the citations come from. `tests/…/test_templates_and_polish.py` runs the engine's own sentences through the chat pipeline's grounding validator, in all three locales.
- **The citation goes INSIDE the sentence**, before the full stop. The validator splits on punctuation, so a trailing marker is a second "sentence" and the claim reads as uncited — perfectly cited text failing its own gate.
- **A module composed from snapshots must come back citing one** (CL-008 §4). Structural, checked before the vocabulary test: `GroundingValidator` decides claim-hood from words, so a times-only sentence passes uncited — an edge case in chat, every morning in a template.
- **Four outcomes, and they are not interchangeable.** POLISHED · RANKING_ONLY (§7.1's COST LEVER, and the §8 provider-outage path) · VERIFIED_CORE_CARDS (§7.1's DEGRADE — diagram 5's `fail` edge, or facts too thin) · FAILED. **An outage is not a grounding failure** — `PolishReport.all_rejected` excludes it deliberately.
- **The DEGRADE has two entrances and the second one was missing.** The grounding `fail` edge worked; "facts too thin" could not fire, because `rank`'s base modules are a superset of what `core_cards` wants under the same `emittable` gate — so a fact set that leaves `rank` empty leaves `core_cards` empty too and lands on FAILED. The one way through was an accident of density (LOW skips the panchang row), which meant two users with identical evidence got different honesty. `_is_core_cards_only` is the real trigger and it needs BOTH halves: the fact stage named something missing, AND nothing beyond `ranking.CORE_CARD_MODULES` survived. A core-cards-only morning with every fact in hand is a quiet LOW-density day, not a failure.
- **The three fact-free modules need `available_inputs`, and nothing built it.** `priorities`, `goal_check` and `family_reminder` were structurally unreachable in a real brief for three milestones. `personal_inputs.load_inputs` is the loader, called by BOTH generation paths (the scheduled task and `/v1/today`'s on-open). A slug is not a sentence (localise `profiles.priorities` through `start.priorities.option.*`), a goal is already in the user's words (verbatim, never translated), and a CSFLE name that reads back as ciphertext declines rather than composing a card around a blob.
- **§32.13's key has three components; the unique index has two** (CL-008 §3). Locale rides inside the stored key so §32.7 can tell a stale-language row from a current one; `(user_id, date)` stays unique so a locale change REPLACES rather than duplicates. The §23.4 collapse key omits locale for the mirror-image reason.
- **`brief_time` is zero-padded local "HH:MM"** and the padding is load-bearing: the §7.1 index does a STRING range scan, and unpadded "7:00" sorts after "10:00".
- **Dormancy is the residual tier** (CL-008 §2), never orthogonal to payment — a paying subscriber on holiday must not lose the mornings they paid for.
- **The pre-job works over CELLS, not users.** §7.2's key carries no user by construction, so a city of ten thousand costs what a city of one costs. A pre-job iterating users would produce identical output at ten thousand times the price and nothing downstream would notice.
- **Chart facts ARE wired** — `astrology/chart_adapter.py` calls sitara-astro for natal, dasha and transits, and `CompositeBriefFacts` fetches both halves independently so neither takes the other down. `BriefFacts.missing` names whichever failed, which is what `_missing_reason` reads. (This line said the opposite through M6–M8; it was stale, not a decision.)

## today module (M8-P9b, §28.2/§29.1) — invariants that must not regress
- **`GET /v1/today` is the door M6 never had.** M6 stored `daily_briefings` rows nothing could read. The router is deliberately thin: `BriefStore.get` on the user's LOCAL date (§32.13, never UTC), `generate_on_open` on a miss (§7.1's dormant path and §32.13's missed-date path are one code path), `mark_opened`, serialise. Every other decision is made somewhere better.
- **A failed brief is a SCREEN, not a 5xx.** §28.2 has a designed variant for every way this goes wrong. Returning an error envelope from `/v1/today` would replace a designed state with an error page on the app's home surface.
- **The brief enums live in `sitara_schemas.today`, not here.** `Density`, `Tier`, `BriefStatus` and `BriefDegradeReason` cross the wire, so both sides need one declaration — the same discipline §34.3's `MorningModule` already follows. `types.py` imports and re-exports them; it declares none.
- **`variant` is NOT a payload field.** §32.1's precedence is a rule over `TodayState`, evaluated once in `apps/web/src/lib/today-variant.ts` where the stack is rendered. A server that also picked the variant would be a second implementation, and the two would disagree on exactly the crowded morning the rule exists for.
- **`compose_brief` is the ladder without the store.** Split out of `generate_for` so the four outcomes are reachable with no database, no queue and no clock — which is what let the dev router run the REAL ladder instead of needing a fake `BriefStore`.
- **A festival is nudged, not bypassed.** `_relevance_for` raises `festival_observance`'s relevance when the fact is present, because §28.2 puts a festival on two surfaces and at MED density the card otherwise loses the cut to `family_reminder` — a festival morning rendering no festival anywhere. It is still gated on having the fact (§5.3).
- **Tara's line is NOT an eighteenth module.** §28.2 item (2) is composed by `templates.compose_taras_line` in two registers: cited when it leans on the day, claimless when there are no facts. The claimless register is what makes "always present" compatible with cite-or-die. **A cited line must be ONE sentence** — `_cite` puts the marker before the final stop, so a two-sentence line leaves the claim in sentence one uncited. A parametrised test over every band × locale caught exactly that.
- **`sources_line` is derived from the CONFIDENCE STATE, not the snapshot count.** A module's snapshot count is how many different facts it stands on, not how many sources agreed on one — reading it produced a Trust Sheet saying "checked against two sources" directly above "one source available today". §32.2 already encodes corroboration in the state.
- **`dev_router` is dev-only and mounted by `app.py` only when `environment == "dev"`** — `db.seed`'s rule. It fixes only the FACTS and the account state (`dev_fixtures.py`) and runs the real ranking engine, composer and ladder over them. It carries **no stub model at all**: once the partial degrade path existed, `provider_degraded` reached VERIFIED_CORE_CARDS through the real ladder, and the ungrounded-LLM stub it used to need was deleted.
- **The web's fixtures are RECORDED, never authored.** `scripts/record_today_fixtures.py` writes `apps/web/tests/__fixtures__/today/` from the real pipeline; `stub-api.mjs` replays them. Re-record after any template, ranking or ladder change — the diff is the review artefact.

## memory consolidation (M6, diagram 8) — invariants that must not regress
- **Consolidation never deletes.** Same rule `decay.py` established: §32.4 retains "until user deletes". A duplicate is FOLDED — muted, kept in the vault, pointing at its canonical — because the user consented to each copy separately.
- **The canonical is elected per CLUSTER, not per pair.** Pairwise folding builds chains (A→B, then B→C) that leave a duplicate pointing at a duplicate. Single-link clustering then one election makes that unrepresentable.
- **A muted memory is never folded into** — unmuting must not restore a pointer.
- **`theme_label` is TOP-LEVEL and encrypted**; everything else consolidation writes lives in `consolidation` and is metadata only. The explicit codec reaches top-level paths and not nested ones (§36.3), so a nested label would silently never be encrypted — and a theme name is memory content in summary form.
- **No model, no label.** An unlabelled theme is a real theme; an invented one would be a summary of the user's life that nobody wrote.
- **Nothing crosses an embedding space or a §32.4 type** — cosine across spaces is noise, and noise that clusters looks exactly like insight.

## scheduling module (M6, §6.1/§23.7)
- **Exactly one Beat may run.** Two would double-fire every §7.1 wave. The compose stack runs `beat` as its own single container.
- **Every task must be safe to run twice.** §6.1 rejected a workflow engine on the strength of "Celery Beat + idempotent tasks", and `task_acks_late` means a dead worker hands the message back.
- **The tick fans out by `send_task` name**, so the producer needs none of the consumer's imports and can run on a worker carrying no model client.

## Commands (Today)
- Re-record the web's Today fixtures: `uv run python scripts/record_today_fixtures.py`
- The variant switcher: run the API in dev, then `/en/dev/today` in the web app

## Commands (M6)
- Wave simulation: `uv run python -m sitara_api.daily_guidance.simulate --users 5000`
- Nightly consolidation: `uv run python -m sitara_api.memory.consolidation --dry-run`
- Beat: `celery -A sitara_api.scheduling.celery_app:app beat`
- Workers: `celery -A sitara_api.scheduling.celery_app:app worker -Q brief.paying,brief.trial`

## Commands (M4)
- Build/repair schema: `uv run python -m sitara_api.db.migrate --phase expand`
- Seed dev data: `uv run python -m sitara_api.db.seed --wipe`
- **Verify against §6.4: `uv run python -m sitara_api.db.verify`** (exit 1 on drift)
