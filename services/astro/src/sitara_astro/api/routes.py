"""Facts endpoints — sync `def` so the swisseph lock serialises on the
threadpool without blocking the event loop (§5.2 D5)."""

from fastapi import APIRouter

from sitara_astro.api.models import (
    FactsRequest,
    FactsResponse,
    NumerologyRequest,
    PanchangRequest,
    TransitsRequest,
)
from sitara_astro.engine.factbuild import dasha_facts, natal_facts, transit_facts
from sitara_astro.engine.panchang_factbuild import panchang_facts
from sitara_astro.numerology.factbuild import ConfirmedName, numerology_facts

router = APIRouter(prefix="/v1/facts", tags=["facts"])


@router.post("/natal")
def compute_natal(request: FactsRequest) -> FactsResponse:
    return FactsResponse(
        facts=natal_facts(
            request.birth,
            request.options,
            subject=request.subject,
            chart_version=request.chart_version,
        )
    )


@router.post("/dasha")
def compute_dasha(request: FactsRequest) -> FactsResponse:
    return FactsResponse(
        facts=dasha_facts(
            request.birth,
            request.options,
            subject=request.subject,
            chart_version=request.chart_version,
        )
    )


@router.post("/transits")
def compute_transits_endpoint(request: TransitsRequest) -> FactsResponse:
    return FactsResponse(
        facts=transit_facts(
            request.birth,
            request.options,
            request.transit_date_utc,
            subject=request.subject,
            chart_version=request.chart_version,
        )
    )


@router.post("/panchang")
def compute_panchang(request: PanchangRequest) -> FactsResponse:
    """Layer-A panchang for a local date at an explicit place (§5.2, §30.2).

    Serves two callers: the §8 degradation ladder's internal rung when DivineAPI
    is unreachable, and the Layer-D comparison job's independent third opinion.
    Facts are global (subject = geohash4+tradition) — no user id is accepted.
    """
    return FactsResponse(
        facts=panchang_facts(
            request.local_date,
            request.place,
            request.tradition,
            request.options,
            chart_version=request.chart_version,
            include_day_timings=request.include_day_timings,
        )
    )


@router.post("/numerology")
def compute_numerology(request: NumerologyRequest) -> FactsResponse:
    """Moolank + bhagyank always; name numbers only when §22.10 confirmation
    has happened. An unconfirmed non-Latin name raises ASTRO_NAME_UNCONFIRMED
    so the caller can run the confirmation step — we never guess a spelling.
    """
    name = None
    if request.name_as_entered:
        name = ConfirmedName.from_confirmation(
            request.name_as_entered,
            confirmed=request.name_confirmed,
            edited_latin=request.name_edited_latin,
        )
    return FactsResponse(
        facts=numerology_facts(
            request.dob,
            name,
            request.options,
            subject=request.subject,
            chart_version=request.chart_version,
        )
    )
