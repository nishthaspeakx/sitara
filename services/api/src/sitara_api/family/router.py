"""Family endpoints (§29.1 S27 `/you/family`, S28 `/you/family/[id]`).

Two shapes here are load-bearing rather than stylistic:

* **The deletion takes memory IDS, not a boolean.** §32.15 says the checkbox
  is offered with the candidates "listed", so the client shows what would go
  and sends back what she ticked. A boolean would move the judgement about
  which memories are "about them" from the user to a name match.
* **`GET /{id}/memories` is a separate call from the delete.** The list has to
  be seen before it can be consented to, and an endpoint that both listed and
  deleted would make the confirm step optional.
"""

from __future__ import annotations

import datetime as dt

from bson import ObjectId
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sitara_schemas import ErrorCode

from sitara_api.auth.router import CurrentSession
from sitara_api.errors import ApiError
from sitara_api.family.models import (
    DeletionEffects,
    FamilyMember,
    MemorialState,
    MemoryAboutMember,
    Relation,
)
from sitara_api.family.service import FamilyService

router = APIRouter(prefix="/v1/family", tags=["family"])


class MemberView(BaseModel):
    member_id: str
    relation: Relation
    name: str
    language_tag: str
    has_birth_details: bool
    attested: bool
    #: §45 (CC-012). Served so the family list can render her differently and
    #: the delete sheet can offer the alternative she has not taken yet.
    memorial_state: MemorialState = MemorialState.LIVING
    created_at: dt.datetime | None = None

    @classmethod
    def of(cls, member: FamilyMember) -> MemberView:
        return cls(
            member_id=str(member.member_id),
            relation=member.relation,
            name=member.name,
            language_tag=member.language_tag,
            has_birth_details=member.has_birth_details,
            # The timestamp is §13 evidence and stays server-side; the client
            # needs to know only whether the gate is open.
            attested=member.attested_at is not None,
            memorial_state=member.memorial_state,
            created_at=member.created_at,
        )


class MemoryAboutView(BaseModel):
    """One candidate for §32.15's checkbox, with the content the user needs to
    decide — she is being asked whether to delete THIS, so showing it is the
    whole point."""

    memory_id: str
    type: str
    content: str

    @classmethod
    def of(cls, candidate: MemoryAboutMember) -> MemoryAboutView:
        return cls(
            memory_id=str(candidate.memory_id),
            type=candidate.type,
            content=candidate.content,
        )


class EffectsView(BaseModel):
    """What the deletion did, so the sheet can say so afterwards rather than
    promise it beforehand."""

    birth_details: int
    charts: int
    memories: int
    member_removed: bool
    attestation_retained: bool

    @classmethod
    def of(cls, effects: DeletionEffects) -> EffectsView:
        return cls(
            birth_details=effects.birth_details,
            charts=effects.charts,
            memories=effects.memories,
            member_removed=effects.member_removed,
            attestation_retained=effects.attestation_retained,
        )


class AddMemberRequest(BaseModel):
    relation: Relation
    name: str = Field(min_length=1, max_length=120)
    language_tag: str = Field(default="en", max_length=16)


class EditMemberRequest(BaseModel):
    relation: Relation | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    language_tag: str | None = Field(default=None, max_length=16)


class MemorialRequest(BaseModel):
    """§45's conversion, both directions.

    A state rather than a `remember: true` flag, because §45.2 makes it
    reversible and a one-way verb would quietly say otherwise.
    """

    memorial_state: MemorialState


class DeleteMemberRequest(BaseModel):
    """§32.15's sheet, as a request.

    `delete_memory_ids` empty IS the default-keep promise — there is no
    "delete all memories" flag, because §32.15 says listed and a flag is the
    opposite of listed.
    """

    delete_memory_ids: list[str] = Field(default_factory=list, max_length=500)


def _service(request: Request) -> FamilyService:
    service: FamilyService | None = getattr(request.app.state, "family_service", None)
    if service is None:
        raise ApiError(ErrorCode.SYS_UNAVAILABLE, "errors.sys.unavailable")
    return service


def _user_id(session: tuple[ObjectId, str]) -> ObjectId:
    return session[0]


def _object_id(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except Exception:
        raise ApiError(ErrorCode.SYS_VALIDATION) from None


@router.get("", response_model=list[MemberView])
async def list_members(request: Request, session: CurrentSession) -> list[MemberView]:
    """S27. §30.5: family guidance appears in the account-holder's spaces only."""
    members = await _service(request).list_members(_user_id(session))
    return [MemberView.of(m) for m in members]


@router.post("", response_model=MemberView, status_code=201)
async def add_member(
    payload: AddMemberRequest, request: Request, session: CurrentSession
) -> MemberView:
    member = await _service(request).add(
        owner_user_id=_user_id(session),
        relation=payload.relation,
        name=payload.name,
        language_tag=payload.language_tag,
    )
    return MemberView.of(member)


@router.get("/{member_id}", response_model=MemberView)
async def get_member(
    member_id: str, request: Request, session: CurrentSession
) -> MemberView:
    member = await _service(request).get(_user_id(session), _object_id(member_id))
    if member is None:
        raise ApiError(ErrorCode.SYS_VALIDATION, "errors.family.not_found")
    return MemberView.of(member)


@router.patch("/{member_id}", response_model=MemberView)
async def edit_member(
    member_id: str, payload: EditMemberRequest, request: Request, session: CurrentSession
) -> MemberView:
    member = await _service(request).edit(
        owner_user_id=_user_id(session),
        member_id=_object_id(member_id),
        relation=payload.relation,
        name=payload.name,
        language_tag=payload.language_tag,
    )
    if member is None:
        raise ApiError(ErrorCode.SYS_VALIDATION, "errors.family.not_found")
    return MemberView.of(member)


@router.post("/{member_id}/attest", response_model=MemberView)
async def attest(member_id: str, request: Request, session: CurrentSession) -> MemberView:
    """§13's attestation checkbox. Its own endpoint because it is its own act:
    the account-holder asserting she has the right to enter someone else's
    birth details, recorded permanently in the §6.4 consent ledger."""
    member = await _service(request).attest_birth_details(
        owner_user_id=_user_id(session), member_id=_object_id(member_id)
    )
    if member is None:
        raise ApiError(ErrorCode.SYS_VALIDATION, "errors.family.not_found")
    return MemberView.of(member)


@router.post("/{member_id}/memorial", response_model=MemberView)
async def set_memorial_state(
    member_id: str,
    payload: MemorialRequest,
    request: Request,
    session: CurrentSession,
) -> MemberView:
    """§32.15's alternative, offered on the same sheet as the deletion (§45).

    Its own endpoint rather than a field on the delete request, and that is
    not tidiness: they are opposite acts. One destroys birth details, charts
    and — if she ticks them — memories; this one writes a single field and
    touches nothing else. Sharing a request body would put them one boolean
    apart.
    """
    member = await _service(request).set_memorial_state(
        owner_user_id=_user_id(session),
        member_id=_object_id(member_id),
        state=payload.memorial_state,
    )
    if member is None:
        raise ApiError(ErrorCode.SYS_VALIDATION, "errors.family.not_found")
    return MemberView.of(member)


@router.get("/{member_id}/memories", response_model=list[MemoryAboutView])
async def memories_about(
    member_id: str, request: Request, session: CurrentSession
) -> list[MemoryAboutView]:
    """§32.15's "listed". Read before the delete sheet renders its checkboxes."""
    candidates = await _service(request).memories_about(
        owner_user_id=_user_id(session), member_id=_object_id(member_id)
    )
    return [MemoryAboutView.of(c) for c in candidates]


@router.post("/{member_id}/delete", response_model=EffectsView)
async def delete_member(
    member_id: str,
    payload: DeleteMemberRequest,
    request: Request,
    session: CurrentSession,
) -> EffectsView:
    """§32.15.

    A POST rather than a DELETE for the reason the journal's deletion gives:
    it carries a body, and a DELETE with a body is a thing intermediaries may
    drop. Losing it here would silently mean "keep every memory" — the safe
    direction, but by accident rather than by decision.
    """
    effects = await _service(request).delete(
        owner_user_id=_user_id(session),
        member_id=_object_id(member_id),
        delete_memory_ids=[_object_id(m) for m in payload.delete_memory_ids],
    )
    if not effects.member_removed:
        raise ApiError(ErrorCode.SYS_VALIDATION, "errors.family.not_found")
    return EffectsView.of(effects)


__all__ = ["EffectsView", "MemberView", "MemoryAboutView", "router"]
