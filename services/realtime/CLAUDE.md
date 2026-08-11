# services/realtime — WebSocket chat/voice service (SPEC §6.1, §34.6)

Slim FastAPI service dedicated to WS sessions (independent scaling, sticky routing). Speaks ONLY the §34.6 protocol: binary = 16kHz mono PCM with 8-byte header (4B seq + 4B flags); text = JSON control events from the CLOSED set in `sitara_schemas.ws_events`.

Two sockets. `WS /chat/session` is S18's and it is REAL — §34.6 over the actual §9 pipeline. `WS /call/session` is still the M0 stub; §33.5 makes live calls a conditional release gate and M9 owns the audio path.

## Rules
- Never invent a control event type — the set is closed; additions are §31.3 change control in packages/schemas.
- Call audio is NEVER stored (§33.1). Heartbeat 10s, reap 30s, resume window 5 min, else handoff.to_text with context (§34.6).
- Full protocol behaviour (VAD ducking, barge-in, metering, degrade ladder) is M9 — keep the M0 stub honest until then.

## The chat socket (M8-P10, §25.4/§34.6) — invariants that must not regress
- **This service holds no pipeline, no model client and no database.** Every turn is `sitara-api`'s, over `POST /v1/chat/ws/turn`. A second copy of §9 would be a second set of validators to keep in step, and the one that drifts is the one nobody is looking at.
- **`captions.partial` is NEVER emitted for Tara, and it is structural.** §9 runs grounding, language-quality and safety-post AFTER generation, so streamed tokens would race three validators to the screen. This service never holds a draft: the turn stream carries stage NAMES and then one validated `ChatTurn`, so there is no expression here that could forward pre-validation text. That is the fabrication gate — not a rule someone remembers.
- **A text conversation is said in the fifteen members that already exist.** A typed message is the same event a spoken one produces after STT — a finalised caption. The mapping is written down once, in `packages/schemas/src/ws-events.json`, so both services read one description.
- **Heartbeat is the transport's ping/pong**, which is exactly why the closed set has no heartbeat member to invent. Reap at 30s (§29.2).
- **A completed turn is BUFFERED, never re-run** (§32.11). Re-running on reconnect would charge a user twice for one question and could answer the same words differently. It is buffered BEFORE the send, or a socket that died between the pipeline answering and the frame leaving would lose exactly the turn the window exists for.
- **`ResumeBuffer` is process-local and that is stated, not overlooked.** §6.1's sticky routing makes a same-instance reconnect the normal case; a redeploy costs a `resume.offer` and gives `handoff.to_text`, which is a designed state. Redis is a scaling decision for when the losses are measured.
- **`STAGE_PRESENCE` is a deliberate partial map.** A §9 stage it does not name emits nothing, so a stage added in M9 cannot start animating a presence state nobody designed.
- **One turn at a time.** A second question mid-flight is refused with `SYS_RATE_LIMITED` rather than interleaved. The test HOLDS the first turn open — an earlier version just sent two messages quickly, the mock answered the first before the second was read, and the guard was never reached.
- **Binary frames are refused on the chat socket until M9.** A socket that quietly accepts PCM has opened a §33.1 storage question nobody asked.

## Commands
- Run: `uv run uvicorn sitara_realtime.main:app --port 8002 --reload`
- Test: `uv run pytest -q` · Lint: `uv run ruff check .` · Types: `uv run pyright`
