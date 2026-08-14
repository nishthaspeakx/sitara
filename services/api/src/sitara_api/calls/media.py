"""The media socket between `sitara-realtime` and `sitara-api` (M10, §25.3).

The FRAME SET itself is not here. It lives in
`packages/schemas/src/call-media.json` → `sitara_schemas.call_media`, because
both services name it and this package's own rule is that a set both sides of a
wire name belongs in one declaration before either side reads it. That rule was
learned four times — the confidence states, the presence states, the memory
types, the voice vocabulary — each time by two implementations drifting while
nothing consumed the value. This is the first one to arrive before the drift.

What remains here is the API side's end of the socket: the two headers
`sitara-realtime` presents, and the reasoning about why the socket exists at
all, which the source JSON also carries for the other reader.
"""

from __future__ import annotations

from sitara_schemas.call_media import (
    CALL_TICK_INTERVAL_S,
    CallDownFrame,
    CallUpFrame,
)

__all__ = [
    "CALL_TICK_INTERVAL_S",
    "SERVICE_KEY_HEADER",
    "WS_SESSION_HEADER",
    "CallDownFrame",
    "CallUpFrame",
]

#: The headers realtime presents. The service key is checked FIRST and fails
#: closed on an unset expected value (`require_service_key`), because this
#: socket runs the §9 pipeline on behalf of whatever user the ws_session names —
#: an unconfigured guard here is an open door that looks shut.
SERVICE_KEY_HEADER = "X-Sitara-Service-Key"
WS_SESSION_HEADER = "X-Sitara-WS-Session"
