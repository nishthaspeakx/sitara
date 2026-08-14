"""Night-reflection endpoints (§24.4 S19, §28.2's night variant).

The route is `/v1/reflection/{local_date}` and the date is a PATH parameter
rather than a server-side "today". §27 binds a reflection to the user's local
calendar day at creation, and only the client knows which day that is for her
— a server that substituted its own would move a traveller's reflection to a
day she was not there for.
"""

from __future__ import annotations

import datetime as dt

from bson import ObjectId
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sitara_schemas import ErrorCode

from sitara_api.auth.router import CurrentSession
from sitara_api.errors import ApiError
from sitara_api.reflection.models import PROMPT_ORDER, Mood, Prompt, Reflection
from sitara_api.reflection.service import MAX_ENTRY_CHARS, ReflectionService

router = APIRouter(prefix="/v1/reflection", tags=["reflection"])

_ISO_DATE = 10


class EntryView(BaseModel):
    prompt: Prompt
    text: str


class ReflectionView(BaseModel):
    date: str
    locale: str
    entries: list[EntryView]
    mood: Mood | None = None
    memory_chips: list[str] = Field(default_factory=list)
    #: The ceremony's order, served rather than hard-coded client-side, so the
    #: three prompts have one declaration (§34.3's discipline for the module
    #: enum, applied to a smaller closed set).
    prompt_order: list[Prompt] = Field(default_factory=lambda: list(PROMPT_ORDER))
    started: bool = False

    @classmethod
    def of(cls, reflection: Reflection) -> ReflectionView:
        return cls(
            date=reflection.date,
            locale=reflection.locale,
            entries=[EntryView(prompt=e.prompt, text=e.text) for e in reflection.entries],
            mood=reflection.mood,
            memory_chips=list(reflection.memory_chips),
            prompt_order=list(PROMPT_ORDER),
            started=reflection.is_started,
        )

    @classmethod
    def empty(cls, date: str, locale: str) -> ReflectionView:
        """A night not yet written is an empty reflection, not a 404.

        §24.6 forbids dead ends, and the night takeover opens straight onto
        this surface — a 404 on the first tap would be the app telling her she
        had not done something.
        """
        return cls(
            date=date,
            locale=locale,
            entries=[],
            mood=None,
            memory_chips=[],
            prompt_order=list(PROMPT_ORDER),
            started=False,
        )


class SaveRequest(BaseModel):
    locale: str = Field(min_length=2, max_length=16)
    entries: dict[Prompt, str] = Field(default_factory=dict)
    mood: Mood | None = None
    memory_chips: list[str] = Field(default_factory=list, max_length=11)


def _service(request: Request) -> ReflectionService:
    service: ReflectionService | None = getattr(request.app.state, "reflection_service", None)
    if service is None:
        raise ApiError(ErrorCode.SYS_UNAVAILABLE, "errors.sys.unavailable")
    return service


def _user_id(session: tuple[ObjectId, str]) -> ObjectId:
    return session[0]


def _valid_date(value: str) -> str:
    """An ISO local date, validated here so a malformed one cannot mint a row.

    `night_reflections` has a unique index on `(user_id, date)`, so a garbage
    date is a permanent garbage row rather than a transient error.
    """
    if len(value) != _ISO_DATE:
        raise ApiError(ErrorCode.SYS_VALIDATION, "errors.reflection.bad_date")
    try:
        dt.date.fromisoformat(value)
    except ValueError:
        raise ApiError(ErrorCode.SYS_VALIDATION, "errors.reflection.bad_date") from None
    return value


@router.get("/{local_date}", response_model=ReflectionView)
async def get_reflection(
    local_date: str, request: Request, session: CurrentSession, locale: str = "en"
) -> ReflectionView:
    reflection = await _service(request).get(_user_id(session), _valid_date(local_date))
    if reflection is None:
        return ReflectionView.empty(local_date, locale)
    return ReflectionView.of(reflection)


@router.put("/{local_date}", response_model=ReflectionView)
async def save_reflection(
    local_date: str, payload: SaveRequest, request: Request, session: CurrentSession
) -> ReflectionView:
    """Create or continue tonight's reflection.

    A PUT because it is idempotent on (user, date) — she may send the whole
    reflection as often as she likes, and §6.4's unique index means the second
    send updates rather than duplicates.
    """
    for text in payload.entries.values():
        if len(text) > MAX_ENTRY_CHARS:
            raise ApiError(ErrorCode.SYS_VALIDATION, "errors.reflection.too_long")

    reflection = await _service(request).save(
        user_id=_user_id(session),
        date=_valid_date(local_date),
        locale=payload.locale,
        entries=payload.entries,
        mood=payload.mood,
        memory_chips=payload.memory_chips,
    )
    return ReflectionView.of(reflection)


__all__ = ["EntryView", "ReflectionView", "router"]
