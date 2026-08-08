"""Chat turn endpoint (§6.3, §25.4).

One POST per turn. The response carries the reply, the §5.4 confidence state
and the full fact snapshots (§34.2) so the Trust Sheet renders from what was
served, not from a recomputation. Fact-IDs stay internal: §30.4 is explicit
that they "remain internal (logs/admin) and never render to users", so the
snapshots travel and the ids are not surfaced as a user-facing list.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field
from sitara_schemas import ErrorCode
from sitara_schemas.facts import ConfidenceState, FactSnapshot

from sitara_api.chat_orchestration.pipeline import ChatPipeline
from sitara_api.chat_orchestration.types import BirthProfile, TurnRequest
from sitara_api.errors import ApiError

router = APIRouter(prefix="/v1/chat", tags=["chat"])


class TurnPayload(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=4000)
    #: The account locale (§2.4). The reply is always in this locale.
    locale: str = Field(min_length=2, max_length=10)
    place_label: str | None = Field(default=None, max_length=120)


class TurnResponse(BaseModel):
    text: str
    locale: str
    confidence: ConfidenceState
    intent: str
    safety_level: str
    presence_state: int
    trace_id: str
    fact_snapshots: list[FactSnapshot] = []
    message_key: str | None = None
    review_queued: bool = False
    budget_notice_key: str | None = None
    message_id: str | None = None


@router.post("/turn", response_model=TurnResponse)
async def chat_turn(
    payload: TurnPayload,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> TurnResponse:
    pipeline: ChatPipeline | None = getattr(request.app.state, "chat_pipeline", None)
    if pipeline is None:
        raise ApiError(ErrorCode.SYS_UNAVAILABLE, "errors.sys.unavailable")

    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise ApiError(ErrorCode.AUTH_INVALID_TOKEN)

    profile: BirthProfile = getattr(request.state, "birth_profile", None) or BirthProfile()
    result = await pipeline.run(
        TurnRequest(
            user_id=str(user_id),
            conversation_id=payload.conversation_id,
            text=payload.text,
            locale=payload.locale,
            now=dt.datetime.now(dt.UTC),
            profile=profile,
            place_label=payload.place_label,
        )
    )
    return TurnResponse(
        text=result.text,
        locale=result.locale,
        confidence=result.confidence,
        intent=result.intent.value,
        safety_level=result.safety.level.name,
        presence_state=int(result.presence_state),
        trace_id=result.trace_id,
        fact_snapshots=list(result.fact_snapshots),
        message_key=result.message_key,
        review_queued=result.review_queued,
        budget_notice_key=result.budget_notice_key,
        message_id=result.message_id,
    )
