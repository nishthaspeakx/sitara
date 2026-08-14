"""sitara-realtime — WebSocket chat/voice service (SPEC §6.1, §34.6).

Two sockets on one protocol.

`WS /chat/session` is S18's, and it is real: it speaks the §34.6 control-event
set over the actual §9 pipeline, reached through `sitara-api`. See `chat.py`
for the mapping of a text conversation onto fifteen voice-shaped members, and
for why `captions.partial` is never emitted for Tara.

`WS /call/session` is M10's, and it is real: §25.3's live call, said in the same
fifteen members. See `call.py` for the division of labour with `sitara-api` and
for why every branch of the degrade ladder ends in `handoff.to_text`.

Freezing the event set in M0 and building the text chat on it first paid for
itself here — the transport, the heartbeat, the resume window and the handoff
were all already exercised, so M10 was not discovering them for the first time
under a live microphone.

**This service holds no database, no model client and no pipeline.** Every turn
is `sitara-api`'s. A second copy of §9 would be a second set of validators to
keep in step, and the one that drifts is the one nobody is looking at.
"""


from fastapi import FastAPI, WebSocket

from sitara_realtime import __version__
from sitara_realtime.call import call_socket
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
    """M10's socket — §25.3's live call, in the same fifteen members.

    No longer the M0 stub. §33.5 still gates whether calls SHIP, and the gate is
    evaluated where a call is granted rather than here: `POST /v1/call/session`
    refuses on the flag, on CC-010's locale ruling and on an exhausted §7.3
    pool, so a call that must not happen never reaches this handler.
    """
    await call_socket(ws, ws.app.state.settings, ws.app.state.resume_buffer)
