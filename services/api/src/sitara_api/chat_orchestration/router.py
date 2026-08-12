"""Chat turn endpoints (§6.3, §25.4, §34.6).

Two transports, one turn. `POST /v1/chat/turn` is the plain request/response
door — the browser's own origin, cookie-authenticated, and §32.11's handoff
path when the socket is gone. The `/ws/*` pair is what `sitara-realtime` calls
on the user's behalf so the §34.6 socket can speak to the real §9 pipeline
without a second copy of it.

Both serve the same `ChatTurn` (`sitara_schemas.chat`), because a turn that
renders one way over HTTP and another over the socket is two chat screens
wearing one name.

**Fact snapshots no longer travel.** This module used to serve them whole "so
the Trust Sheet renders from what was served" — and a `FactSnapshot` carries
its `fact_id`, which §30.4 says never renders to users. §28.2's payload has
been held to the stricter reading since M8 (no field one could travel in, and a
parity test asserting the absence); now that `presenter.py` renders §30.4's
three layers server-side there is nothing the snapshots were for, and
`ChatTurn` is held to the same standard.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
from collections.abc import AsyncIterator, Callable

from fastapi import APIRouter, Header, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sitara_schemas import ErrorCode
from sitara_schemas.chat import ChatTurn

from sitara_api.auth.router import CurrentSession
from sitara_api.chat_orchestration.pipeline import ChatPipeline
from sitara_api.chat_orchestration.presenter import present_turn
from sitara_api.chat_orchestration.types import BirthProfile, Stage, TurnRequest
from sitara_api.chat_orchestration.ws_session import (
    WS_SESSION_TTL_S,
    WsGrant,
    WsTicketService,
    require_service_key,
)
from sitara_api.errors import ApiError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/chat", tags=["chat"])


class TurnPayload(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=4000)
    #: The account locale (§2.4). The reply is always in this locale.
    locale: str = Field(min_length=2, max_length=10)
    place_label: str | None = Field(default=None, max_length=120)
    #: §25.4's swipe-to-reply. The quoted turn reaches the PIPELINE, not just
    #: the drawing — §25.4 says "the pipeline receives the quoted turn
    #: explicitly", so a quote that only rendered would be the feature's
    #: appearance without its substance.
    quoted_message_id: str | None = Field(default=None, max_length=64)


class SessionPayload(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=64)
    locale: str = Field(min_length=2, max_length=10)


class SessionGrantResponse(BaseModel):
    """What the browser needs to open the socket, and nothing more."""

    ticket: str
    ws_url: str
    resume_window_s: int


class RedeemPayload(BaseModel):
    ticket: str = Field(min_length=1, max_length=128)


class RedeemResponse(BaseModel):
    ws_session: str
    user_id: str
    conversation_id: str
    locale: str
    expires_in_s: int


class WsTurnPayload(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    quoted_message_id: str | None = Field(default=None, max_length=64)


def _pipeline(request: Request) -> ChatPipeline:
    pipeline: ChatPipeline | None = getattr(request.app.state, "chat_pipeline", None)
    if pipeline is None:
        raise ApiError(ErrorCode.SYS_UNAVAILABLE, "errors.sys.unavailable")
    return pipeline


def _tickets(request: Request) -> WsTicketService:
    return WsTicketService(request.app.state.redis)


async def _birth_profile(request: Request, user_id: str) -> BirthProfile:
    """What the pipeline knows about the subject (§5.3 step 2).

    **This used to read `request.state.birth_profile`, which nothing ever
    set.** Every live turn therefore ran with an all-False `BirthProfile()`,
    `required_data` declined for a missing date of birth, and the chat could
    not answer a single chart question against a real account — including
    accounts whose birth row was on file. Every test passed a profile in
    explicitly, so nothing caught it; the first live conversation did, on its
    first question.

    §13's single door to birth details is the astrology facade, so this asks
    it rather than reading the collection. It narrows to the four booleans and
    the zone the pipeline is allowed to see: §5.3 is explicit that the
    orchestrator gets sufficiency, never values.

    A facade failure degrades to "we do not know" rather than raising. That is
    the honest direction — Tara asks for the birth date she cannot confirm she
    has, which is a worse answer but never a wrong one.
    """
    facade = getattr(request.app.state, "astrology", None)
    if facade is None:
        return BirthProfile()
    try:
        birth = await facade.birth_input(user_id)
    except Exception:
        logger.warning("birth profile unavailable; answering without a chart")
        return BirthProfile()
    if birth is None:
        return BirthProfile()

    place = bool(birth.place_name) and bool(birth.tz)
    return BirthProfile(
        has_date=True,
        has_exact_time=birth.has_exact_time,
        # §10-6's four accuracies collapse to two questions here: do we have a
        # usable instant, and failing that do we have a window? A row with no
        # time at all is the Moon-chart path (§5.3), not a window.
        has_time_window=not birth.has_exact_time,
        has_place=place,
        tz=birth.tz,
    )


async def _run(
    request: Request,
    *,
    user_id: str,
    conversation_id: str,
    text: str,
    locale: str,
    place_label: str | None = None,
    quoted_message_id: str | None = None,
    on_stage: Callable[[Stage], None] | None = None,
) -> ChatTurn:
    pipeline = _pipeline(request)
    profile = await _birth_profile(request, user_id)
    result = await pipeline.run(
        TurnRequest(
            user_id=user_id,
            conversation_id=conversation_id,
            text=text,
            locale=locale,
            now=dt.datetime.now(dt.UTC),
            profile=profile,
            place_label=place_label,
            quoted_message_id=quoted_message_id,
        ),
        on_stage=on_stage,
    )
    return present_turn(result)


@router.post("/turn", response_model=ChatTurn)
async def chat_turn(
    payload: TurnPayload,
    request: Request,
    session: CurrentSession,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ChatTurn:
    # §34.5: the httpOnly session cookie is the only way a product API learns
    # who is calling. `request.state.user_id` is set by nothing — reading it
    # would 401 every legitimately signed-in user.
    user_id, _session_id = session
    return await _run(
        request,
        user_id=str(user_id),
        conversation_id=payload.conversation_id,
        text=payload.text,
        locale=payload.locale,
        place_label=payload.place_label,
        quoted_message_id=payload.quoted_message_id,
    )


# ---------------------------------------------------------------------------
# The socket's door (§34.6) — ws_session.py records why a ticket and not a cookie
# ---------------------------------------------------------------------------


@router.post("/session", response_model=SessionGrantResponse)
async def chat_session(
    payload: SessionPayload, request: Request, session: CurrentSession
) -> SessionGrantResponse:
    """Mint the single-use ticket the browser opens the socket with.

    `ws_url` is SERVED, not compiled into the client — the same reasoning
    `lib/api.ts` records for the API origin. A public build-time constant that
    has to agree with a cookie posture and a deployment topology is not a
    configuration option; it is a way for the two to disagree silently.
    """
    user_id, session_id = session
    settings = request.app.state.settings
    ticket = await _tickets(request).mint_ticket(
        WsGrant(
            user_id=str(user_id),
            session_id=session_id,
            conversation_id=payload.conversation_id,
            locale=payload.locale,
        )
    )
    return SessionGrantResponse(
        ticket=ticket,
        ws_url=settings.realtime_ws_url,
        resume_window_s=settings.chat_resume_window_s,
    )


@router.post("/ws/redeem", response_model=RedeemResponse)
async def chat_ws_redeem(
    payload: RedeemPayload,
    request: Request,
    service_key: str | None = Header(default=None, alias="X-Sitara-Service-Key"),
) -> RedeemResponse:
    """`sitara-realtime` burns a ticket and receives the socket's own token."""
    require_service_key(service_key, request.app.state.settings.service_key)
    ws_session, grant = await _tickets(request).redeem_ticket(payload.ticket)
    return RedeemResponse(
        ws_session=ws_session,
        user_id=grant.user_id,
        conversation_id=grant.conversation_id,
        locale=grant.locale,
        expires_in_s=WS_SESSION_TTL_S,
    )


@router.post("/ws/turn")
async def chat_ws_turn(
    payload: WsTurnPayload,
    request: Request,
    service_key: str | None = Header(default=None, alias="X-Sitara-Service-Key"),
    ws_session: str | None = Header(default=None, alias="X-Sitara-WS-Session"),
) -> StreamingResponse:
    """The real §9 pipeline, streamed as it advances.

    NDJSON, one object per line: `{"stage": …}` for each §9 stage the pipeline
    completes, then exactly one `{"turn": …}` or `{"error": …}` as the last
    line. `sitara-realtime` maps the stage frames onto §34.6 `presence.state`
    events, which is what makes §25.4's typing indicator *real* rather than a
    timer pretending to be one.

    **A stage frame carries a stage NAME and nothing else.** No draft, no
    partial text, no token. §9 puts grounding, language-quality and safety-post
    AFTER generation, so any pre-validation text on this stream would be a
    fabricated claim racing three validators to the user's screen. There is no
    field here it could travel in — the same guarantee `ChatTurn` gives one
    level up, and the reason `captions.partial` is never emitted for Tara.
    """
    require_service_key(service_key, request.app.state.settings.service_key)
    if not ws_session:
        raise ApiError(ErrorCode.AUTH_FORBIDDEN, "errors.auth.forbidden")
    grant = await _tickets(request).resolve_session(ws_session)

    stages: asyncio.Queue[str | None] = asyncio.Queue()

    def on_stage(stage: Stage) -> None:
        stages.put_nowait(stage.value)

    async def body() -> AsyncIterator[bytes]:
        task = asyncio.create_task(
            _run(
                request,
                user_id=grant.user_id,
                conversation_id=grant.conversation_id,
                text=payload.text,
                locale=grant.locale,
                quoted_message_id=payload.quoted_message_id,
                on_stage=on_stage,
            )
        )
        task.add_done_callback(lambda _: stages.put_nowait(None))

        while True:
            stage = await stages.get()
            if stage is None:
                break
            yield json.dumps({"stage": stage}).encode() + b"\n"

        try:
            turn = await task
        except ApiError as exc:
            # The socket needs the §34.4 envelope to forward, not a 500 with a
            # truncated stream: the client has a designed state for an envelope
            # and none for a response that simply stops.
            yield (
                json.dumps(
                    {"error": {"code": exc.code.value, "message_key": exc.message_key}}
                ).encode()
                + b"\n"
            )
            return
        except Exception:
            logger.exception("ws turn failed", extra={"conversation": grant.conversation_id})
            yield (
                json.dumps(
                    {
                        "error": {
                            "code": ErrorCode.SYS_INTERNAL.value,
                            "message_key": "errors.sys.internal",
                        }
                    }
                ).encode()
                + b"\n"
            )
            return
        yield json.dumps({"turn": turn.model_dump(mode="json")}).encode() + b"\n"

    return StreamingResponse(body(), media_type="application/x-ndjson")
