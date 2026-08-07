"""Public panchang endpoints (§6.3 module boundary, §30.2 explicit place).

Three surfaces:
  GET  /v1/panchang                — the day's tithi/nakshatra for a place
  GET  /v1/panchang/day-timings    — choghadiya + rahu kaal / yamaganda / gulikai
  POST /v1/muhurat                 — windows for an EXPLICIT place (§30.2)

Every response carries its sources and confidence, because a fact without its
provenance cannot be rendered on a Trust Sheet (§13) and cite-or-die applies
above this layer too (§5.3).
"""

import datetime as dt

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field
from sitara_schemas.facts import ConfidenceState, FactSnapshot, FactSource, MuhuratType, Tradition

from sitara_api.panchang.places import PlaceResolver, resolve_explicit
from sitara_api.panchang.service import PanchangResult, PanchangService

router = APIRouter(tags=["panchang"])


class PlaceOut(BaseModel):
    """§30.2: every timing is labelled with the city it was computed for."""

    label: str
    tz: str


class PanchangResponse(BaseModel):
    facts: list[FactSnapshot]
    confidence: ConfidenceState
    sources: list[FactSource]
    place: PlaceOut
    disputed: bool = False
    cached: bool = False
    degraded: bool = False


class ExplicitPlaceIn(BaseModel):
    """A place the caller states outright — "the wedding is in Jaipur"."""

    label: str = Field(min_length=1, max_length=120)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    tz: str = Field(min_length=1)


class MuhuratRequest(BaseModel):
    """§30.2: "any muhurat query accepts an explicit place ('wedding in
    Jaipur') — computed for THAT place with its timezone, labelled with city".

    Either `city` (gazetteer lookup) or `place` (fully specified). The place is
    never inferred from the session: an event elsewhere is the normal case.
    """

    muhurat_type: MuhuratType = MuhuratType.GENERAL
    date_from: dt.date
    date_to: dt.date
    city: str | None = None
    place: ExplicitPlaceIn | None = None
    tradition: Tradition = Tradition.AMANTA


def _respond(result: PanchangResult) -> PanchangResponse:
    return PanchangResponse(
        facts=result.facts,
        confidence=result.confidence,
        sources=list(result.sources),
        place=PlaceOut(label=result.place.label, tz=result.place.tz),
        disputed=result.disputed,
        cached=result.cached,
        degraded=result.degraded,
    )


def _service(request: Request) -> PanchangService:
    return request.app.state.panchang_service


def _resolver(request: Request) -> PlaceResolver:
    return request.app.state.place_resolver


def _resolve(request: Request, city: str | None, place: ExplicitPlaceIn | None):
    """An unknown city is declined with ASTRO_PLACE_UNRESOLVED — never
    substituted with a default, which would produce confidently wrong timings
    for the wrong place (§5.3)."""
    if place is not None:
        return resolve_explicit(place.label, place.lat, place.lon, place.tz)
    return _resolver(request).resolve_city(city or "")


@router.get("/v1/panchang", response_model=PanchangResponse)
async def get_panchang(
    request: Request,
    date: dt.date,
    city: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    tz: str | None = None,
    label: str | None = None,
    tradition: Tradition = Tradition.AMANTA,
) -> PanchangResponse:
    explicit = (
        ExplicitPlaceIn(label=label or "", lat=lat, lon=lon, tz=tz)
        if lat is not None and lon is not None and tz is not None
        else None
    )
    place = _resolve(request, city, explicit)
    return _respond(await _service(request).panchang(date, place, tradition))


@router.get("/v1/panchang/day-timings", response_model=PanchangResponse)
async def get_day_timings(
    request: Request,
    date: dt.date,
    city: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    tz: str | None = None,
    label: str | None = None,
    tradition: Tradition = Tradition.AMANTA,
) -> PanchangResponse:
    """Choghadiya plus the rahu-kaal/yamaganda/gulikai bands.

    Framing note (§9/§13): an inauspicious band is rendered as a neutral
    caution window, never as fear-selling copy — the API states quality, the
    client states it kindly.
    """
    explicit = (
        ExplicitPlaceIn(label=label or "", lat=lat, lon=lon, tz=tz)
        if lat is not None and lon is not None and tz is not None
        else None
    )
    place = _resolve(request, city, explicit)
    return _respond(await _service(request).day_timings(date, place, tradition))


@router.post("/v1/muhurat", response_model=PanchangResponse)
async def find_muhurat(
    request: Request, payload: MuhuratRequest, _idempotency_key: str | None = Query(default=None)
) -> PanchangResponse:
    place = _resolve(request, payload.city, payload.place)
    result = await _service(request).muhurat(
        payload.muhurat_type,
        payload.date_from,
        payload.date_to,
        place,
        payload.tradition,
    )
    return _respond(result)
