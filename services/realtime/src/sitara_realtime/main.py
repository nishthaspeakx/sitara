"""sitara-realtime — WebSocket chat/voice service (SPEC §6.1, §34.6).

M0 walking skeleton: /healthz + a WS /call/session stub that speaks the
§34.6 protocol's opening move (session.ready) using the SHARED typed
contract from sitara_schemas. Full protocol behaviour (VAD, barge-in,
heartbeats, resume, handoff) lands in M9 — the closed event set is already
frozen here.
"""

import time

from fastapi import FastAPI, WebSocket
from sitara_schemas import ControlEvent, ControlEventType

from sitara_realtime import __version__

app = FastAPI(title="sitara-realtime", version=__version__)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "sitara-realtime", "version": __version__}


@app.websocket("/call/session")
async def call_session(ws: WebSocket) -> None:
    """M0 stub: accept, emit a typed session.ready, close on client end."""
    await ws.accept()
    ready = ControlEvent(
        type=ControlEventType.SESSION_READY,
        seq=0,
        ts=time.time() * 1000,
        payload={},
    )
    await ws.send_text(ready.model_dump_json())
    # Echo loop placeholder until M9 implements the full §34.6 protocol.
    try:
        while True:
            await ws.receive_text()
    except Exception:
        return
