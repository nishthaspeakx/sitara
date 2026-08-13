"""sitara-realtime — WebSocket chat/voice service (SPEC §6.1, §34.6).

Two sockets on one protocol.

`WS /chat/session` is S18's, and it is real: it speaks the §34.6 control-event
set over the actual §9 pipeline, reached through `sitara-api`. See `chat.py`
for the mapping of a text conversation onto fifteen voice-shaped members, and
for why `captions.partial` is never emitted for Tara.

`WS /call/session` is still the M0 stub. Full voice behaviour (VAD, barge-in,
TTS chunking, the degrade ladder) is M9; the closed event set was frozen here
in M0 and the text chat has now exercised the transport, the heartbeat, the
resume window and the handoff — which is most of what M9 would otherwise be
discovering for the first time under a microphone.

**This service holds no database, no model client and no pipeline.** Every turn
is `sitara-api`'s. A second copy of §9 would be a second set of validators to
keep in step, and the one that drifts is the one nobody is looking at.
"""

import time

from fastapi import FastAPI, WebSocket
from sitara_schemas import ControlEvent, ControlEventType

from sitara_realtime import __version__
from sitara_realtime.chat import ResumeBuffer, chat_socket
from sitara_realtime.config import Settings

app = FastAPI(title="sitara-realtime", version=__version__)
app.state.settings = Settings()
#: Process-local, and `ResumeBuffer`'s docstring states the consequence: a
#: redeploy inside someone's five-minute window costs them a `resume.offer`
#: and gives them `handoff.to_text` instead, which is a designed state.
app.state.resume_buffer = ResumeBuffer()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "sitara-realtime", "version": __version__}


@app.websocket("/chat/session")
async def chat_session(ws: WebSocket) -> None:
    """S18's socket — §34.6 over the real §9 pipeline."""
    await chat_socket(ws, ws.app.state.settings, ws.app.state.resume_buffer)


@app.websocket("/call/session")
async def call_session(ws: WebSocket) -> None:
    """M0 stub: accept, emit a typed session.ready, close on client end.

    Left as a stub deliberately. §33.5 makes live calls a conditional release
    gate, and M9 owns the audio path; a half-built duplex here would be the
    kind of code that looks finished in a demo and has never carried a packet.
    """
    await ws.accept()
    ready = ControlEvent(
        type=ControlEventType.SESSION_READY,
        seq=0,
        ts=time.time() * 1000,
        payload={},
    )
    await ws.send_text(ready.model_dump_json())
    # Echo loop placeholder until M9 implements the full §34.6 audio path.
    try:
        while True:
            await ws.receive_text()
    except Exception:
        return
