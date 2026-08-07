# services/realtime — WebSocket chat/voice service (SPEC §6.1, §34.6)

Slim FastAPI service dedicated to WS sessions (independent scaling, sticky routing). Speaks ONLY the §34.6 protocol: binary = 16kHz mono PCM with 8-byte header (4B seq + 4B flags); text = JSON control events from the CLOSED set in `sitara_schemas.ws_events`.

## Rules
- Never invent a control event type — the set is closed; additions are §31.3 change control in packages/schemas.
- Call audio is NEVER stored (§33.1). Heartbeat 10s, reap 30s, resume window 5 min, else handoff.to_text with context (§34.6).
- Full protocol behaviour (VAD ducking, barge-in, metering, degrade ladder) is M9 — keep the M0 stub honest until then.

## Commands
- Run: `uv run uvicorn sitara_realtime.main:app --port 8002 --reload`
- Test: `uv run pytest -q` · Lint: `uv run ruff check .` · Types: `uv run pyright`
