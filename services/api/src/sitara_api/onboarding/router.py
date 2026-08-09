"""Endpoints for the §24.4 onboarding stack (S02–S13).

Every route is behind `CurrentSession` except place lookup, which needs no
identity and reads a committed gazetteer. §33.2's product identity comes from
the §34.5 session cookie; nothing here takes a user id from the request body.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Annotated, Any

from bson import ObjectId
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field
from sitara_schemas import ErrorCode
from sitara_schemas.facts import ConfidenceState, Tradition

from sitara_api.astrology.service import TIME_ACCURACY, BirthDetailsInput
from sitara_api.auth.router import CurrentSession
from sitara_api.errors import ApiError
from sitara_api.onboarding import reading as reading_module
from sitara_api.onboarding.service import OnboardingService, StepAnswers
from sitara_api.onboarding.types import DegradeReason, FirstReading, ReadingStatus, SourceState
from sitara_api.panchang.places import resolve_explicit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["onboarding"])

#: How long the ceremony waits on the engine before answering with what it has.
#:
#: §0.17 puts the first reading at minute 3 of a five-minute covenant, and
#: §24.4 asks every onboarding screen for "skeleton→content ≤400ms". Neither
#: survives an unbounded wait on a cold natal computation, and a request that
#: hangs server-side becomes a spinner client-side. Six seconds is long enough
#: for a real cold chart and short enough that the honest partial arrives while
#: she is still looking at the screen.
READING_DEADLINE_SECONDS = 6.0


# ---------------------------------------------------------------------------
# Wire models
# ---------------------------------------------------------------------------


class PlaceIn(BaseModel):
    label: str
    lat: float
    lon: float
    tz: str


class StepPatch(BaseModel):
    """One screen's answer. Absent means "not this screen", never "clear it"."""

    locale: str | None = None
    interest: str | None = None
    priorities: list[str] | None = None
    display_name: str | None = None
    latin_name: str | None = None
    city: PlaceIn | None = None
    brief_time: str | None = None
    voice_enabled: bool | None = None
    completed_step: int | None = None


class ConsentIn(BaseModel):
    #: §10-5's three S05 cards. Memory consent is DEFERRED to the first chip and
    #: voice consent to first voice use, so neither is grantable here — a client
    #: that sent one would be recording a consent the user was never shown.
    types: list[str] = Field(min_length=1, max_length=3)


class BirthIn(BaseModel):
    date: dt.date
    place: PlaceIn
    time_accuracy: str
    time: dt.time | None = None
    part_of_day: str | None = None


class StateOut(BaseModel):
    locale: str
    completed_steps: list[int]
    next_step: int
    has_birth_details: bool
    time_accuracy: str | None
    has_city: bool
    interest: str | None
    priorities: list[str]
    display_name: str | None
    brief_time: str | None
    voice_enabled: bool


class PlaceOut(BaseModel):
    id: str
    label: str
    lat: float
    lon: float
    tz: str


class LineOut(BaseModel):
    id: str
    values: dict[str, str]
    fact_ids: list[str]
    confidence: ConfidenceState
    house: int | None = None


class ReadingOut(BaseModel):
    status: ReadingStatus
    confidence: ConfidenceState
    #: §30.4 — what the source row is allowed to claim. The client must not
    #: hardcode "verified against 2 sources"; that is a fact about today.
    source_state: SourceState
    lines: list[LineOut]
    #: §34.2 — the full snapshots, embedded. `dict` rather than a typed model
    #: because `FactSnapshot`'s value is a discriminated union the client only
    #: ever round-trips, never interprets.
    facts: list[dict[str, Any]]
    missing: list[str]
    degrade_reason: DegradeReason | None


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------


def _service(request: Request) -> OnboardingService:
    return OnboardingService(request.app.state.db, getattr(request.app.state, "astrology", None))


def _user(session: tuple[ObjectId, str]) -> ObjectId:
    return session[0]


ALLOWED_CONSENTS = ("essential", "birth_data", "marketing")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/onboarding", response_model=StateOut)
async def get_state(request: Request, session: CurrentSession) -> StateOut:
    """§24.4's resume. Returns where to continue, never the birth details."""
    state = await _service(request).state(_user(session))
    return StateOut(
        locale=state.locale,
        completed_steps=list(state.completed_steps),
        next_step=state.next_step,
        has_birth_details=state.has_birth_details,
        time_accuracy=state.time_accuracy,
        has_city=state.has_city,
        interest=state.interest,
        priorities=list(state.priorities),
        display_name=state.display_name,
        brief_time=state.brief_time,
        voice_enabled=state.voice_enabled,
    )


@router.patch("/onboarding", response_model=StateOut)
async def patch_state(payload: StepPatch, request: Request, session: CurrentSession) -> StateOut:
    answers = StepAnswers(
        locale=payload.locale,
        interest=payload.interest,
        priorities=payload.priorities,
        display_name=payload.display_name,
        latin_name=payload.latin_name,
        city=payload.city.model_dump() if payload.city else None,
        brief_time=payload.brief_time,
        voice_enabled=payload.voice_enabled,
        completed_step=payload.completed_step,
    )
    await _service(request).apply(_user(session), answers)
    return await get_state(request, session)


@router.post("/onboarding/consents", response_model=StateOut)
async def post_consents(payload: ConsentIn, request: Request, session: CurrentSession) -> StateOut:
    unknown = [t for t in payload.types if t not in ALLOWED_CONSENTS]
    if unknown:
        # A consent type we do not recognise is a consent nobody was shown a
        # card for, and the ledger is legal (§13). Refuse rather than record.
        logger.warning("unknown consent type refused", extra={"types": unknown})
        raise ApiError(ErrorCode.SYS_VALIDATION)
    service = _service(request)
    for consent_type in payload.types:
        await service.record_consent(_user(session), consent_type)
    return await get_state(request, session)


@router.put("/onboarding/birth", response_model=StateOut)
async def put_birth(payload: BirthIn, request: Request, session: CurrentSession) -> StateOut:
    if payload.time_accuracy not in TIME_ACCURACY:
        raise ApiError(ErrorCode.SYS_VALIDATION)
    # The zone is validated against the IANA tzdb here, not trusted: §5.2 never
    # takes a timezone from a vendor OR a client without checking it.
    place = resolve_explicit(payload.place.label, payload.place.lat, payload.place.lon, payload.place.tz)
    try:
        details = BirthDetailsInput(
            date=payload.date,
            place_label=place.label,
            lat=place.lat,
            lon=place.lon,
            tz=place.tz,
            time_accuracy=payload.time_accuracy,
            time=payload.time,
            part_of_day=payload.part_of_day,
        )
    except ValueError:
        # §5.3: "exact" with no time, or a part-of-day naming no window. Never
        # filled in with a guess.
        raise ApiError(ErrorCode.SYS_VALIDATION) from None
    await _service(request).set_birth(_user(session), details)
    return await get_state(request, session)


@router.get("/places", response_model=list[PlaceOut])
async def search_places(
    request: Request, q: Annotated[str, Query(min_length=1, max_length=64)]
) -> list[PlaceOut]:
    """S06/S08 typeahead over the committed gazetteer (§30.2).

    Prefix match, not fuzzy: a wrong city produces confidently-wrong timings
    (§5.3), and a fuzzy matcher that offers Jaipur for "jai" alongside Jaisalmer
    is a place for that to happen quietly.
    """
    resolver = request.app.state.place_resolver
    needle = q.strip().casefold()
    hits = [c for c in resolver.cities if c.label.casefold().startswith(needle)]
    if not hits:
        hits = [c for c in resolver.cities if needle in c.label.casefold()]
    return [
        PlaceOut(id=c.id, label=c.label, lat=c.lat, lon=c.lon, tz=c.tz) for c in hits[:8]
    ]


@router.post("/readings/first", response_model=ReadingOut)
async def first_reading(request: Request, session: CurrentSession) -> ReadingOut:
    """S13 — the ceremony (§0.17 minute 3).

    This endpoint never raises for a missing fact. Every way the reading can
    come up short is a `status`/`degrade_reason` on a 200, because the screen's
    contract is that it always renders SOMETHING honest: a 5xx here would put
    the client into a generic error path on the most important screen in the
    product, where §24.6 wants a specific, warm, in-locale sentence.
    """
    import asyncio

    service = _service(request)
    user_id = _user(session)
    state = await service.state(user_id)

    place = None
    raw_place = (await request.app.state.db.profiles.find_one({"user_id": user_id}) or {}).get(
        "brief_place"
    )
    if raw_place:
        try:
            place = resolve_explicit(
                raw_place.get("label", ""), raw_place["lat"], raw_place["lon"], raw_place["tz"]
            )
        except (ApiError, KeyError):
            logger.warning("first reading: stored place unusable")

    local_date = dt.datetime.now(dt.UTC).date()
    if place is not None:
        from zoneinfo import ZoneInfo

        local_date = dt.datetime.now(ZoneInfo(place.tz)).date()

    degrade: DegradeReason | None = None
    chart = None
    panchang: tuple = ()
    source_state = SourceState.SINGLE
    try:
        chart, panchang, degrade, source_state = await asyncio.wait_for(
            reading_module.gather(
                facade=getattr(request.app.state, "astrology", None),
                panchang_service=getattr(request.app.state, "panchang_service", None),
                user_id=str(user_id),
                local_date=local_date,
                timezone=place.tz if place else "Asia/Kolkata",
                place=place,
                tradition=Tradition.AMANTA,
            ),
            timeout=READING_DEADLINE_SECONDS,
        )
    except TimeoutError:
        # The engine is alive but slow. Say so honestly and let the day's
        # guidance fill in on Today, rather than holding the ceremony open.
        logger.warning("first reading: engine exceeded the ceremony deadline")
        degrade = DegradeReason.TIMEOUT

    result: FirstReading = reading_module.compose(
        chart=chart,
        panchang=panchang,
        locale=state.locale,
        time_accuracy=state.time_accuracy,
        degrade_reason=degrade,
        source_state=source_state,
    )
    await _log_guidance(request, user_id, result)
    return ReadingOut(
        status=result.status,
        confidence=result.confidence,
        source_state=result.source_state,
        lines=[
            LineOut(
                id=line.id.value,
                values=line.values,
                fact_ids=list(line.fact_ids),
                confidence=line.confidence,
                house=line.house,
            )
            for line in result.lines
        ],
        facts=[f.model_dump(mode="json") for f in result.facts],
        missing=list(result.missing),
        degrade_reason=result.degrade_reason,
    )


async def _log_guidance(request: Request, user_id: ObjectId, result: FirstReading) -> None:
    """§34.2 — the artefact embeds the snapshot it cited, at generation.

    A best-effort write: the ceremony must not fail because an audit row did.
    The row is what makes "which reading did she actually see?" answerable
    months later, when the engine has moved on and the chart has been recomputed.
    """
    from sitara_api.db.documents import stamp

    try:
        await request.app.state.db.guidance_logs.insert_one(
            stamp(
                {
                    "user_id": user_id,
                    "surface": "first_reading",
                    "confidence": result.confidence.value,
                    "source_state": result.source_state.value,
                    "status": result.status.value,
                    "degrade_reason": result.degrade_reason.value if result.degrade_reason else None,
                    "line_ids": [line.id.value for line in result.lines],
                    "fact_ids": [fid for line in result.lines for fid in line.fact_ids],
                    "facts": [f.model_dump(mode="json") for f in result.facts],
                }
            )
        )
    except Exception:  # noqa: BLE001
        logger.warning("first reading: guidance log write failed", exc_info=True)
