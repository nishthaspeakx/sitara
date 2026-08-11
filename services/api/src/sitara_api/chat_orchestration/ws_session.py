"""The chat socket's door (§34.5, §34.6, §6.2).

Why this exists at all
----------------------

§34.5's session cookies are httpOnly and first-party, and §6.2 has the browser
call its own origin so they are carried. That works for every HTTP call, because
Next proxies `/auth` and `/v1`. It cannot work for the socket: Next evaluates
its rewrites into a routes manifest at build time and does not proxy an upgrade,
so the browser opens the socket against `sitara-realtime`'s own origin — where a
host-only, SameSite=Lax cookie is simply not sent.

Three ways out were considered. Widening the cookie to `Domain=.sitara.app` so
the handshake is same-site works in dev (cookies ignore ports) and quietly
broadens the cookie's reach in production, which is a security posture change
made to avoid a plumbing problem. Putting a token in JavaScript is what §34.5
exists to prevent. What is left is a ticket:

    browser  --cookie-->  POST /v1/chat/session      →  ticket (60s, single-use)
    browser  --ticket-->  WS  sitara-realtime/chat/session
    realtime --ticket-->  POST /v1/chat/ws/redeem    →  ws_session (30 min)
    realtime --session--> POST /v1/chat/ws/turn      →  the real §9 pipeline

So the browser holds a credential that is single-use, expires in a minute, and
authorises exactly one thing: opening a chat socket. The long-lived token never
leaves the server side. `POST /v1/chat/turn` is untouched and remains the
§32.11 handoff path when the socket is gone.

The tokens are the shape `auth/sessions.py` already uses — opaque random,
sha256-digested as the Redis key, TTL on the key itself. Two differences, both
deliberate: the ticket is deleted on read (single use), and neither token can
authenticate anything except the chat endpoints, because nothing else looks
them up.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

from sitara_schemas import ErrorCode

from sitara_api.db import Redis
from sitara_api.errors import ApiError

#: One minute is long enough for a page to open a socket and short enough that
#: a ticket leaked into a log or a proxy trace is worthless by the time anyone
#: reads it.
TICKET_TTL_S = 60

#: The socket's own lifetime. Refreshed on every turn, so an active
#: conversation never expires mid-thread and an abandoned tab stops costing a
#: key. Deliberately not the access-cookie TTL: this credential lives on a
#: server, not in a browser, and is not refreshed by a rotating cookie.
WS_SESSION_TTL_S = 30 * 60

_TICKET_KEY = "chat:ws_ticket:{digest}"
_SESSION_KEY = "chat:ws_session:{digest}"


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class WsGrant:
    """Who the socket is for, and about what."""

    user_id: str
    session_id: str
    conversation_id: str
    locale: str

    def encode(self) -> str:
        return "\x1f".join((self.user_id, self.session_id, self.conversation_id, self.locale))

    @staticmethod
    def decode(raw: str) -> WsGrant:
        user_id, session_id, conversation_id, locale = raw.split("\x1f")
        return WsGrant(user_id, session_id, conversation_id, locale)


class WsTicketService:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def mint_ticket(self, grant: WsGrant) -> str:
        ticket = secrets.token_urlsafe(32)
        await self._redis.set(
            _TICKET_KEY.format(digest=_digest(ticket)), grant.encode(), ex=TICKET_TTL_S
        )
        return ticket

    async def redeem_ticket(self, ticket: str) -> tuple[str, WsGrant]:
        """Burn the ticket, mint the socket's session token.

        `getdel` rather than get-then-delete: two sockets presenting the same
        ticket must not both be granted, and a check followed by a delete is a
        race that a retrying client produces on its own without any attacker.
        """
        raw = await self._redis.getdel(_TICKET_KEY.format(digest=_digest(ticket)))
        if raw is None:
            raise ApiError(ErrorCode.AUTH_INVALID_TOKEN, "errors.auth.invalid_token")
        grant = WsGrant.decode(raw.decode() if isinstance(raw, bytes) else str(raw))
        ws_session = secrets.token_urlsafe(32)
        await self._redis.set(
            _SESSION_KEY.format(digest=_digest(ws_session)),
            grant.encode(),
            ex=WS_SESSION_TTL_S,
        )
        return ws_session, grant

    async def resolve_session(self, ws_session: str) -> WsGrant:
        key = _SESSION_KEY.format(digest=_digest(ws_session))
        raw = await self._redis.get(key)
        if raw is None:
            raise ApiError(ErrorCode.VOICE_SESSION_NOT_FOUND, "errors.voice.session_not_found")
        # A turn is proof the conversation is alive.
        await self._redis.expire(key, WS_SESSION_TTL_S)
        return WsGrant.decode(raw.decode() if isinstance(raw, bytes) else str(raw))

    async def end_session(self, ws_session: str) -> None:
        await self._redis.delete(_SESSION_KEY.format(digest=_digest(ws_session)))


def require_service_key(presented: str | None, expected: str | None) -> None:
    """Only `sitara-realtime` may call the redeem/turn endpoints.

    Fails CLOSED on an unset expected key. A service-to-service endpoint whose
    guard is disabled when unconfigured is an open endpoint that looks guarded —
    and this one runs the pipeline on behalf of a user id it is handed.

    `compare_digest`, because the comparison is against a secret and the
    endpoint is reachable often enough for a timing signal to accumulate.
    """
    if not expected:
        raise ApiError(ErrorCode.SYS_UNAVAILABLE, "errors.sys.unavailable")
    if not presented or not hmac.compare_digest(presented, expected):
        raise ApiError(ErrorCode.AUTH_FORBIDDEN, "errors.auth.forbidden")
