"""Memory Vault endpoints (§30.5 `/you/memories`, §32.4).

§30.5: "the 11 typed facts with consent stamps — never a content archive."
The API mirrors that. It returns the type, the content the user consented to,
the consent stamp and whether the source still exists — and never an
embedding, which is derived data (§32.5) and 1024 floats nobody asked for.

Deletion is hard deletion (diagram 8), and the scoped-effect endpoints are
separate verbs rather than flags: §30.5 gives "delete a journal entry" and
"delete a conversation" genuinely different consequences, and a boolean would
invite one to be mistaken for the other.
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
from sitara_api.memory.models import (
    ConsentRequired,
    MedicalContentDeclined,
    Memory,
    MemoryCandidate,
    SourceState,
)
from sitara_api.memory.service import MemoryService
from sitara_api.memory.taxonomy import RECONFIRM_WORDING, MemoryType

router = APIRouter(prefix="/v1/memories", tags=["memory"])


class MemoryView(BaseModel):
    """One vault row. No embedding, ever."""

    memory_id: str
    type: MemoryType
    content: str
    consent_granted_at: dt.datetime
    wording_reconfirmed: bool
    muted: bool
    source_state: SourceState
    decay_score: float
    created_at: dt.datetime | None = None

    @classmethod
    def of(cls, memory: Memory) -> MemoryView:
        return cls(
            memory_id=str(memory.memory_id),
            type=memory.type,
            content=memory.content,
            consent_granted_at=memory.consent.granted_at,
            wording_reconfirmed=memory.consent.wording_reconfirmed,
            muted=memory.visibility.muted,
            source_state=memory.visibility.source_state,
            decay_score=memory.decay_score,
            created_at=memory.created_at,
        )


class AcceptChipRequest(BaseModel):
    """The user tapped "remember this". §32.4's only path into the vault."""

    type: MemoryType
    content: str = Field(min_length=1, max_length=2000)
    #: Required for types 7–9 (§32.4 re-confirms their wording before save).
    wording_reconfirmed: bool = False
    source_message_id: str | None = None


class EditRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class MuteRequest(BaseModel):
    muted: bool


class ScopedDeleteRequest(BaseModel):
    """§30.5's two scoped effects, named as what they are."""

    message_ids: list[str] = Field(default_factory=list, max_length=500)
    #: The journal-deletion checkbox: "memories sourced from it survive unless
    #: also deleted". Ignored by the conversation endpoint, which never deletes.
    delete_memories: bool = False


def _service(request: Request) -> MemoryService:
    service: MemoryService | None = getattr(request.app.state, "memory_service", None)
    if service is None:
        raise ApiError(ErrorCode.SYS_UNAVAILABLE, "errors.sys.unavailable")
    return service


def _user_id(session: tuple[ObjectId, str]) -> ObjectId:
    """§33.2: Mongo `_id` is the product identity, and §34.5's session cookie
    is how a product API learns it."""
    return session[0]


def _object_id(value: str, code: ErrorCode = ErrorCode.SYS_VALIDATION) -> ObjectId:
    try:
        return ObjectId(value)
    except Exception:
        raise ApiError(code) from None


@router.get("", response_model=list[MemoryView])
async def list_memories(
    request: Request,
    session: CurrentSession,
    # §30.5: "Vault filters use exactly these 11 labels" — the query parameter
    # is named `type` because that is the label the client filters on.
    type_: Annotated[list[MemoryType] | None, Query(alias="type")] = None,
) -> list[MemoryView]:
    """§30.5's vault list. Shows decayed and muted memories too — it is the
    user's inventory of what Tara knows, not a retrieval ranking."""
    memories = await _service(request).vault(_user_id(session), types=type_)
    return [MemoryView.of(memory) for memory in memories]


@router.post("", response_model=MemoryView, status_code=201)
async def accept_chip(
    payload: AcceptChipRequest, request: Request, session: CurrentSession
) -> MemoryView:
    service = _service(request)
    candidate = MemoryCandidate(
        type=payload.type,
        content=payload.content,
        source_message_id=(
            _object_id(payload.source_message_id) if payload.source_message_id else None
        ),
    )
    try:
        memory = await service.accept_chip(
            user_id=_user_id(session),
            candidate=candidate,
            wording_reconfirmed=payload.wording_reconfirmed,
        )
    except ConsentRequired:
        # §32.4: types 7–9 need their wording re-confirmed. The client shows
        # the wording again; it does not retry with the flag flipped.
        raise ApiError(ErrorCode.SYS_VALIDATION, "errors.memory.reconfirm_wording") from None
    except MedicalContentDeclined:
        raise ApiError(ErrorCode.SAFE_CONTENT_BLOCKED, "errors.memory.medical_declined") from None
    return MemoryView.of(memory)


@router.patch("/{memory_id}", response_model=MemoryView)
async def edit_memory(
    memory_id: str, payload: EditRequest, request: Request, session: CurrentSession
) -> MemoryView:
    """§30.5: "correct a memory" → future guidance uses the corrected version."""
    memory = await _service(request).edit(
        user_id=_user_id(session),
        memory_id=_object_id(memory_id),
        content=payload.content,
    )
    if memory is None:
        raise ApiError(ErrorCode.SYS_VALIDATION, "errors.memory.not_found")
    return MemoryView.of(memory)


@router.post("/{memory_id}/mute", response_model=MemoryView)
async def mute_memory(
    memory_id: str, payload: MuteRequest, request: Request, session: CurrentSession
) -> MemoryView:
    """§30.5's "don't remember this" — withheld from retrieval, kept in the
    vault, reversible. Deletion is the other endpoint and is not reversible."""
    memory = await _service(request).mute(
        user_id=_user_id(session), memory_id=_object_id(memory_id), muted=payload.muted
    )
    if memory is None:
        raise ApiError(ErrorCode.SYS_VALIDATION, "errors.memory.not_found")
    return MemoryView.of(memory)


@router.delete("/{memory_id}", status_code=204)
async def forget_memory(memory_id: str, request: Request, session: CurrentSession) -> None:
    """Hard delete, embedding included (diagram 8).

    §30.5 states the scope at the confirm step, which is the client's job:
    "Tara stops knowing it; past journal text unchanged".
    """
    deleted = await _service(request).forget(
        user_id=_user_id(session), memory_id=_object_id(memory_id)
    )
    if not deleted:
        raise ApiError(ErrorCode.SYS_VALIDATION, "errors.memory.not_found")


@router.post("/scoped/journal-entry-deleted")
async def journal_entry_deleted(
    payload: ScopedDeleteRequest, request: Request, session: CurrentSession
) -> dict[str, int]:
    """§30.5: memories sourced from a deleted journal entry survive unless the
    user ticked the box. `delete_memories` IS the box."""
    deleted = await _service(request).on_journal_entry_deleted(
        user_id=_user_id(session),
        message_ids=[_object_id(m) for m in payload.message_ids],
        delete_memories=payload.delete_memories,
    )
    return {"deleted": deleted}


@router.post("/scoped/conversation-deleted")
async def conversation_deleted(
    payload: ScopedDeleteRequest, request: Request, session: CurrentSession
) -> dict[str, int]:
    """§30.5: dependent memory sources are marked "source removed". The
    memories survive — consent to Tara knowing them did not expire with the
    thread they came from."""
    marked = await _service(request).on_conversation_deleted(
        user_id=_user_id(session),
        message_ids=[_object_id(m) for m in payload.message_ids],
    )
    return {"source_removed": marked}


__all__ = ["RECONFIRM_WORDING", "MemoryView", "router"]
