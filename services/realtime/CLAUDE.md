# services/realtime — WebSocket chat/voice service (SPEC §6.1, §34.6)

Slim FastAPI service dedicated to WS sessions (independent scaling, sticky routing). Speaks ONLY the §34.6 protocol: binary = 16kHz mono PCM with 8-byte header (4B seq + 4B flags); text = JSON control events from the CLOSED set in `sitara_schemas.ws_events`.

Two sockets, both real. `WS /chat/session` is S18's — §34.6 over the actual §9 pipeline, and since M9 it also carries §25.4's voice notes. `WS /call/session` is M9-P10b's: §25.3's live call, said in the same fifteen members. §33.5 still gates whether calls SHIP, and that gate is evaluated where a call is GRANTED (`POST /v1/call/session`), not in the socket.

## Rules
- Never invent a control event type — the set is closed; additions are §31.3 change control in packages/schemas.
- Call audio is NEVER stored (§33.1). Heartbeat 10s, reap 30s, resume window 5 min, else handoff.to_text with context (§34.6).
- The full protocol behaviour (VAD ducking, barge-in, metering, degrade ladder) is M9-P10b's and lives in `call.py`.

## The chat socket (M8-P10, §25.4/§34.6) — invariants that must not regress
- **This service holds no pipeline, no model client and no database.** Every turn is `sitara-api`'s, over `POST /v1/chat/ws/turn`. A second copy of §9 would be a second set of validators to keep in step, and the one that drifts is the one nobody is looking at.
- **`captions.partial` is NEVER emitted for Tara, and it is structural.** §9 runs grounding, language-quality and safety-post AFTER generation, so streamed tokens would race three validators to the screen. This service never holds a draft: the turn stream carries stage NAMES and then one validated `ChatTurn`, so there is no expression here that could forward pre-validation text. That is the fabrication gate — not a rule someone remembers.
- **A text conversation is said in the fifteen members that already exist.** A typed message is the same event a spoken one produces after STT — a finalised caption. The mapping is written down once, in `packages/schemas/src/ws-events.json`, so both services read one description.
- **Heartbeat is the transport's ping/pong**, which is exactly why the closed set has no heartbeat member to invent. Reap at 30s (§29.2).
- **A completed turn is BUFFERED, never re-run** (§32.11). Re-running on reconnect would charge a user twice for one question and could answer the same words differently. It is buffered BEFORE the send, or a socket that died between the pipeline answering and the frame leaving would lose exactly the turn the window exists for.
- **`ResumeBuffer` is process-local and that is stated, not overlooked.** §6.1's sticky routing makes a same-instance reconnect the normal case; a redeploy costs a `resume.offer` and gives `handoff.to_text`, which is a designed state. Redis is a scaling decision for when the losses are measured.
- **`STAGE_PRESENCE` is a deliberate partial map.** A §9 stage it does not name emits nothing, so a stage added in M9 cannot start animating a presence state nobody designed.
- **One turn at a time.** A second question mid-flight is refused with `SYS_RATE_LIMITED` rather than interleaved. The test HOLDS the first turn open — an earlier version just sent two messages quickly, the mock answered the first before the second was read, and the guard was never reached.
- **Binary frames are admissible ONLY inside a `vad.state` bracket** (M9). That is narrower than "accepted" on purpose: the bracket is what binds a run of PCM to a `client_message_id`, a locale and a consent posture, and audio arriving with none of those attached is audio nobody can account for — §33.1 being a section about accounting for audio. Outside a bracket it is still `SYS_VALIDATION`.
- **A sequence gap fails the note and drops the bracket.** A note missing its middle still transcribes, into a fluent sentence the user never said, which then reaches §9 as their question and gets answered. No downstream validator catches it: §9 gates what Tara says, and this fabrication is on the user's side of the turn. Dropping the bracket too stops a client "continuing" into a note that already lost its middle.
- **The cancel-slide sends nothing anywhere** (§28.3). Not transcribed, not stored, not uploaded — the only reading of "cancel" a user would accept for something they said out loud.
- **`tts.*` follows her `captions.final`, never precedes it.** §25.4's transcript toggle must have the validated words on screen before any audio plays, and they must be the text the audio was rendered from. No `tts.chunk_meta` is emitted for a note: a note is synthesised whole, so there are no chunks, and a fabricated one would make the metering look live. That member is M9-P10b's.

## The call socket (M9-P10b, §25.3/§34.6) — invariants that must not regress
- **The whole file is arranged around one sentence: a dropped call must never lose what was said.** Call audio is never stored (§13/§33.1), so a spoken sentence has no recording to fall back on and no composer to resend from. The API commits each transcript the moment STT finalises it; this side's job is to make every failure end somewhere DESIGNED. **Every branch of `_degrade` ends in `handoff.to_text` and none ends in a bare close.**
- **`_closed` and `_degraded` are two flags because they answer two questions.** One flag, set before writing the handoff, made `send` suppress the one frame the whole ladder exists to deliver — the call went quiet and was reaped 30 seconds later. Idempotency is not silence.
- **A sequence gap does NOT fail a call**, and this is the one place that deliberately differs from `chat.Recording`. A voice note with a hole transcribes into a fluent sentence the user never said; a call's lost packet is a lost moment — the user hears themselves misunderstood and says it again. Killing the call would turn a bad second into a lost conversation.
- **Realtime holds the CLOCK; `sitara-api` holds the QUOTA.** §32.9's thresholds, the once-each rule and the exhaustion check all live on the side that can read a subscription. This service sends `tick` with elapsed METERED seconds — not wall clock, because §32.9 stops metering the moment a session is text-mode and §32.11 restarts it only on resume.
- **`SpeechDetector` answers "is the user talking right now?" and nothing else.** It does not segment utterances — the recogniser does, and a second opinion about where a sentence ended would disagree on exactly the hard cases. Onset is 60ms and hangover 500ms: the asymmetry is the defence against a cough, a door, and her own voice leaking out of a phone speaker back into its microphone.
- **The barge-in ATTEMPT and its SUCCESS are reported separately** (§33.5's `barge_in_success`). Reporting both at once would make the ratio 100% by construction — a measure that cannot fail is worse than no measure, because it reads as evidence.
- **`tts_audio_asset_id` is null on a call, and the null is the point.** A note is stored and can be replayed; a call is streamed and never stored, so an invented id would promise a playback control over audio that exists nowhere.
- **The media socket's frame set is `sitara_schemas.call_media`, not a local copy.** Both services name it, which is exactly the condition `packages/schemas`' own rule covers — and this is the first set to land there BEFORE the two sides drifted rather than after.

## Commands
- Run: `uv run uvicorn sitara_realtime.main:app --port 8002 --reload`
- Test: `uv run pytest -q` · Lint: `uv run ruff check .` · Types: `uv run pyright`
