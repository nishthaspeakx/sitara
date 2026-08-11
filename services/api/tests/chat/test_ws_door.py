"""The chat socket's door (§34.5, §34.6) — the ticket, the redemption, the turn.

`ws_session.py` explains why a ticket exists at all: §34.5's cookies are
httpOnly and first-party, Next does not proxy a WebSocket upgrade, and so the
browser opens the socket against another origin where the cookie is not sent.

What is worth testing is not the happy path — it is every way the door could be
left open. A ticket that survives its first use, a service key that is optional
when unset, a ws-session that outlives its conversation: each of those is an
endpoint that runs the §9 pipeline for an arbitrary user id.
"""

from __future__ import annotations

import json

import pytest
from sitara_schemas import ErrorCode

from sitara_api.chat_orchestration.ws_session import (
    TICKET_TTL_S,
    WsGrant,
    WsTicketService,
    require_service_key,
)
from sitara_api.errors import ApiError

pytestmark = pytest.mark.asyncio


class FakeRedis:
    """Enough Redis to hold the two token kinds, with real getdel semantics."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.values[key] = value
        if ex is not None:
            self.ttls[key] = ex

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def getdel(self, key: str) -> str | None:
        return self.values.pop(key, None)

    async def expire(self, key: str, ttl: int) -> None:
        if key in self.values:
            self.ttls[key] = ttl

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)


GRANT = WsGrant(
    user_id="6a70000000000000000000a1",
    session_id="6a70000000000000000000b1",
    conversation_id="6a70000000000000000000c1",
    locale="hi",
)


def _service() -> tuple[WsTicketService, FakeRedis]:
    redis = FakeRedis()
    return WsTicketService(redis), redis  # type: ignore[arg-type]


async def test_a_ticket_is_single_use() -> None:
    """Two sockets presenting one ticket must not both be granted.

    `getdel`, not get-then-delete: the second is a race that an ordinary
    retrying client produces without any attacker involved.
    """
    service, _ = _service()
    ticket = await service.mint_ticket(GRANT)

    ws_session, grant = await service.redeem_ticket(ticket)
    assert grant == GRANT
    assert ws_session

    with pytest.raises(ApiError) as raised:
        await service.redeem_ticket(ticket)
    assert raised.value.code is ErrorCode.AUTH_INVALID_TOKEN


async def test_a_ticket_expires_in_a_minute() -> None:
    """Long enough to open a socket, short enough that one in a proxy log is
    worthless by the time anyone reads it."""
    service, redis = _service()
    await service.mint_ticket(GRANT)

    assert set(redis.ttls.values()) == {TICKET_TTL_S}


async def test_an_unknown_ticket_is_refused_rather_than_guessed() -> None:
    service, _ = _service()
    with pytest.raises(ApiError) as raised:
        await service.redeem_ticket("not-a-ticket")
    assert raised.value.code is ErrorCode.AUTH_INVALID_TOKEN


async def test_the_ws_session_carries_the_grant_and_not_the_clients_word() -> None:
    """The conversation and the locale come from the TICKET, which came from a
    cookie-authenticated call. `sitara-realtime` cannot substitute either, and
    neither can the browser after the fact — which is why `/ws/turn` takes only
    the text and never a user id or a conversation id.
    """
    service, _ = _service()
    ticket = await service.mint_ticket(GRANT)
    ws_session, _ = await service.redeem_ticket(ticket)

    resolved = await service.resolve_session(ws_session)
    assert resolved.user_id == GRANT.user_id
    assert resolved.conversation_id == GRANT.conversation_id
    assert resolved.locale == "hi"


async def test_an_ended_session_stops_resolving() -> None:
    service, _ = _service()
    ticket = await service.mint_ticket(GRANT)
    ws_session, _ = await service.redeem_ticket(ticket)

    await service.end_session(ws_session)
    with pytest.raises(ApiError) as raised:
        await service.resolve_session(ws_session)
    assert raised.value.code is ErrorCode.VOICE_SESSION_NOT_FOUND


async def test_a_grant_survives_a_locale_with_separators_in_it() -> None:
    """`hi-Latn` has a hyphen and a conversation id could hold anything the
    client sent. The encoding uses a unit separator rather than a character
    that appears in the data — a colon-joined grant would have split
    `hi-Latn` fine and an id containing a colon catastrophically."""
    service, _ = _service()
    grant = WsGrant(GRANT.user_id, GRANT.session_id, "c:1:2", "hi-Latn")
    ticket = await service.mint_ticket(grant)

    _, decoded = await service.redeem_ticket(ticket)
    assert decoded == grant


# ---------------------------------------------------------------------------
# The service key
# ---------------------------------------------------------------------------


def test_the_service_key_fails_closed_when_unset() -> None:
    """An unconfigured guard on a service-to-service endpoint is an open door
    that looks shut. `/ws/turn` runs the pipeline for whatever user id the
    grant names, so "no key configured" must mean "refuse", never "allow"."""
    with pytest.raises(ApiError) as raised:
        require_service_key("anything", None)
    assert raised.value.code is ErrorCode.SYS_UNAVAILABLE

    with pytest.raises(ApiError):
        require_service_key(None, "")


def test_a_wrong_or_missing_service_key_is_forbidden() -> None:
    with pytest.raises(ApiError) as raised:
        require_service_key("wrong", "right")
    assert raised.value.code is ErrorCode.AUTH_FORBIDDEN

    with pytest.raises(ApiError):
        require_service_key(None, "right")

    require_service_key("right", "right")  # no raise


# ---------------------------------------------------------------------------
# The streamed turn
# ---------------------------------------------------------------------------


async def test_the_turn_stream_carries_stage_names_and_then_one_turn() -> None:
    """§34.6's `presence.state` events ride on this stream, and §25.4's typing
    indicator rides on those. What must be true of every frame before the last
    is that it names a §9 STAGE and carries nothing else — no draft, no partial
    text, no token. §9 puts three validators after generation, so any
    pre-validation text here would be a fabricated claim racing them to the
    screen.
    """
    from tests.chat.conftest import (
        CONVERSATION_ID,
        NOW,
        SATURN_FACT_ID,
        USER_ID,
        build_env,
    )
    from sitara_api.chat_orchestration.presenter import present_turn
    from sitara_api.chat_orchestration.types import Stage, TurnRequest

    env = build_env()
    fabrication = f"Jupiter rules your 7th house [[{SATURN_FACT_ID}]]."
    env.llm.script("generate", fabrication, fabrication)

    seen: list[Stage] = []
    result = await env.pipeline.run(
        TurnRequest(
            user_id=USER_ID,
            conversation_id=CONVERSATION_ID,
            text="what is Saturn doing?",
            locale="en",
            now=NOW,
            profile=env.profile,
        ),
        on_stage=seen.append,
    )

    # The stages the socket would have relayed, serialised exactly as the
    # router serialises them.
    frames = [json.dumps({"stage": s.value}) for s in seen]
    assert frames, "no stage frames — the typing indicator would be a timer"
    assert Stage.GENERATION in seen
    assert Stage.GROUNDING in seen

    blob = " ".join(frames)
    assert "Jupiter" not in blob
    assert "7th house" not in blob
    for frame in frames:
        assert set(json.loads(frame)) == {"stage"}

    # And the one frame that does carry words carries the VALIDATED ones.
    assert "Jupiter" not in present_turn(result).text


async def test_a_stage_listener_that_raises_never_costs_the_user_the_answer() -> None:
    """Losing a presence event costs an animation. Raising out of the tracer
    would cost the turn."""
    from tests.chat.conftest import CONVERSATION_ID, NOW, SATURN_FACT_ID, USER_ID, build_env
    from sitara_api.chat_orchestration.types import TurnRequest

    env = build_env()
    env.llm.script(
        "generate", f"Saturn is in your 10th house today [[{SATURN_FACT_ID}]]."
    )

    def explode(_stage: object) -> None:
        raise RuntimeError("the socket went away mid-turn")

    result = await env.pipeline.run(
        TurnRequest(
            user_id=USER_ID,
            conversation_id=CONVERSATION_ID,
            text="what is Saturn doing?",
            locale="en",
            now=NOW,
            profile=env.profile,
        ),
        on_stage=explode,
    )

    assert "Saturn" in result.text
    assert result.message_key is None
