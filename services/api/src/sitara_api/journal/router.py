"""Journal endpoints (§30.5, S21–S23).

The API shape follows §30.5's own sentence. `GET /v1/journal` is the calendar
+list of what happened; `GET /v1/journal/{date}` is one day of it;
`GET /v1/journal/search` is keyword+filters over Journal+thread. Saving is a
POST of a pointer (§44.2) and never of content — the endpoint takes no field
that could carry a sentence, which is the same discipline `TrustSheet` uses to
keep fact IDs off a screen.

Deleting an artefact carries §30.5's checkbox explicitly. It is a request
field with a `False` default rather than a server-side policy, because "the
memories survive unless she says otherwise" is a promise made at a confirm
step, and a default that drifts is a user losing memories she chose to keep.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from bson import ObjectId
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field
from sitara_schemas import ErrorCode

from sitara_api.auth.router import CurrentSession
from sitara_api.errors import ApiError
from sitara_api.journal.models import (
    ArtefactType,
    JournalDay,
    JournalEntry,
    JournalSave,
    NotSaveable,
)
from sitara_api.journal.search import SearchFilters, SearchHit, SearchMode
from sitara_api.journal.service import JournalService

router = APIRouter(prefix="/v1/journal", tags=["journal"])

#: §30.5's Journal is a calendar+list, never an infinite feed. A page is a
#: window on it and the client asks for the next one by date.
MAX_DAYS = 120


class EntryView(BaseModel):
    artefact_type: ArtefactType
    ref: str
    local_date: str
    saved: bool = False
    save_id: str | None = None
    note: str | None = None
    #: Rendered from where the artefact lives — the Journal keeps no copy
    #: (§44.2). Null where the source is gone, which the client renders as an
    #: honest absence rather than dropping the row.
    preview: str | None = None
    message_id: str | None = None
    conversation_id: str | None = None
    confidence: str | None = None
    occurred_at: dt.datetime | None = None

    @classmethod
    def of(cls, entry: JournalEntry) -> EntryView:
        return cls(
            artefact_type=entry.artefact_type,
            ref=entry.ref,
            local_date=entry.local_date,
            saved=entry.saved,
            save_id=entry.save_id,
            note=entry.note,
            preview=entry.preview,
            message_id=entry.message_id,
            conversation_id=entry.conversation_id,
            confidence=entry.confidence,
            occurred_at=entry.occurred_at,
        )


class DayView(BaseModel):
    local_date: str
    entries: list[EntryView]

    @classmethod
    def of(cls, day: JournalDay) -> DayView:
        return cls(
            local_date=day.local_date, entries=[EntryView.of(e) for e in day.entries]
        )


class HitView(BaseModel):
    artefact_type: ArtefactType
    ref: str
    local_date: str
    preview: str
    message_id: str | None = None
    conversation_id: str | None = None

    @classmethod
    def of(cls, hit: SearchHit) -> HitView:
        return cls(
            artefact_type=hit.artefact_type,
            ref=hit.ref,
            local_date=hit.local_date,
            preview=hit.preview,
            message_id=hit.message_id,
            conversation_id=hit.conversation_id,
        )


class SaveView(BaseModel):
    save_id: str
    artefact_type: ArtefactType
    artefact_ref: str
    saved_at: dt.datetime
    note: str | None = None

    @classmethod
    def of(cls, save: JournalSave) -> SaveView:
        return cls(
            save_id=str(save.save_id),
            artefact_type=save.artefact_type,
            artefact_ref=save.artefact_ref,
            saved_at=save.saved_at,
            note=save.note,
        )


class SaveRequest(BaseModel):
    """§25.4's "save to journal", and §25.3's call-end chip.

    There is deliberately no `content` field. A save is a pointer (§44.2), so
    a client cannot hand us a sentence to keep even by accident — the same
    reason `TrustSheet` has no prop that can carry a fact ID.
    """

    artefact_type: ArtefactType
    artefact_ref: str = Field(min_length=1, max_length=200)
    message_id: str | None = None
    #: The user's own words about the artefact, not the artefact's words.
    note: str | None = Field(default=None, max_length=1000)


class DeleteArtefactRequest(BaseModel):
    """§30.5's journal-entry deletion, checkbox included."""

    artefact_type: ArtefactType
    artefact_ref: str = Field(min_length=1, max_length=200)
    #: "memories sourced from it survive unless also deleted — offered as a
    #: checkbox" (§30.5). Default False IS the promise.
    delete_memories: bool = False
    #: The turns the artefact was built from, which is how a memory is known
    #: to be sourced from it. Empty means the checkbox has nothing to act on.
    message_ids: list[str] = Field(default_factory=list, max_length=500)


def _service(request: Request) -> JournalService:
    service: JournalService | None = getattr(request.app.state, "journal_service", None)
    if service is None:
        raise ApiError(ErrorCode.SYS_UNAVAILABLE, "errors.sys.unavailable")
    return service


def _user_id(session: tuple[ObjectId, str]) -> ObjectId:
    """§33.2: Mongo `_id` is the product identity."""
    return session[0]


def _object_id(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except Exception:
        raise ApiError(ErrorCode.SYS_VALIDATION) from None


@router.get("", response_model=list[DayView])
async def timeline(
    request: Request,
    session: CurrentSession,
    since: str | None = None,
    until: str | None = None,
) -> list[DayView]:
    """S21 — the calendar+list."""
    days = await _service(request).timeline(_user_id(session), since=since, until=until)
    return [DayView.of(day) for day in days[:MAX_DAYS]]


@router.get("/search", response_model=list[HitView])
async def search(
    request: Request,
    session: CurrentSession,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    type_: Annotated[list[ArtefactType] | None, Query(alias="type")] = None,
    since: str | None = None,
    until: str | None = None,
) -> list[HitView]:
    """S23 — keyword + filters (§30.5's P0).

    Always EXPLICIT: this endpoint exists because a user typed something. The
    suggestion path, where §30.5's L4 rule bites, is a different caller and
    passes a different mode — it is not reachable by omitting a parameter here.
    """
    hits = await _service(request).search(
        _user_id(session),
        query=q,
        filters=SearchFilters(
            types=tuple(type_ or ()), since=since, until=until
        ),
        mode=SearchMode.EXPLICIT,
    )
    return [HitView.of(hit) for hit in hits]


@router.get("/{local_date}", response_model=DayView)
async def day(local_date: str, request: Request, session: CurrentSession) -> DayView:
    """S22 — one date. An empty day is a day (§24.6: no dead ends)."""
    return DayView.of(await _service(request).day(_user_id(session), local_date))


@router.post("/saves", response_model=SaveView, status_code=201)
async def save(payload: SaveRequest, request: Request, session: CurrentSession) -> SaveView:
    try:
        saved = await _service(request).save(
            user_id=_user_id(session),
            artefact_type=payload.artefact_type,
            artefact_ref=payload.artefact_ref,
            message_id=_object_id(payload.message_id) if payload.message_id else None,
            note=payload.note,
        )
    except NotSaveable:
        raise ApiError(ErrorCode.SYS_VALIDATION, "errors.journal.not_saveable") from None
    return SaveView.of(saved)


@router.delete("/saves/{save_id}", status_code=204)
async def unsave(save_id: str, request: Request, session: CurrentSession) -> None:
    """§44.4: removes the pointer and nothing else."""
    removed = await _service(request).unsave(
        user_id=_user_id(session), save_id=_object_id(save_id)
    )
    if not removed:
        raise ApiError(ErrorCode.SYS_VALIDATION, "errors.journal.save_not_found")


@router.post("/delete", response_model=dict[str, int])
async def delete_artefact(
    payload: DeleteArtefactRequest, request: Request, session: CurrentSession
) -> dict[str, int]:
    """§30.5's journal-entry deletion.

    A POST rather than a DELETE because it carries a body — the checkbox and
    the source turns — and a DELETE with a body is a thing intermediaries are
    entitled to drop. Losing the body here would silently flip the checkbox to
    its default, which is the safe direction but the wrong reason.
    """
    return await _service(request).delete_artefact(
        user_id=_user_id(session),
        artefact_type=payload.artefact_type,
        artefact_ref=payload.artefact_ref,
        delete_memories=payload.delete_memories,
        message_ids=[_object_id(m) for m in payload.message_ids],
    )


__all__ = ["MAX_DAYS", "DayView", "EntryView", "HitView", "SaveView", "router"]
