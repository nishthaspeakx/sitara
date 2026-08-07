"""Public numerology facade (§6.3 module boundary, §10-9 / S10 reveal moment).

sitara-astro computes; this service is the only public door to it. Responses
carry the full FactSnapshots (§34.2 — the caller embeds them in the artefact)
plus the §5.4 confidence state that drives Tara's register.
"""

import datetime as dt

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sitara_schemas.facts import ConfidenceState, FactSnapshot

from sitara_api.numerology.adapter import AstroNumerologyAdapter
from sitara_api.numerology.confidence import confidence_for

router = APIRouter(prefix="/v1/numerology", tags=["numerology"])


class NumerologyProfileRequest(BaseModel):
    """§22.10: a non-Latin name must be confirmed before it can be summed.
    Send `name_confirmed=true` to accept the proposal, or `name_edited_latin`
    to override it. Omit the name entirely for the date-only reveal.
    """

    dob: dt.date
    name_as_entered: str | None = Field(default=None, max_length=200)
    name_confirmed: bool = False
    name_edited_latin: str | None = Field(default=None, max_length=200)
    chart_version: int = Field(default=1, ge=1)


class NumerologyProfileResponse(BaseModel):
    facts: list[FactSnapshot]
    confidence: ConfidenceState


@router.post("/profile", response_model=NumerologyProfileResponse)
async def numerology_profile(
    payload: NumerologyProfileRequest, request: Request
) -> NumerologyProfileResponse:
    settings = request.app.state.settings
    adapter: AstroNumerologyAdapter = getattr(
        request.app.state,
        "numerology_adapter",
        AstroNumerologyAdapter(settings.astro_base_url, settings.astro_timeout_seconds),
    )
    # `subject` is the product identity (§33.2 Mongo _id); the session user is
    # the only subject a caller may compute for.
    subject = getattr(request.state, "user_id", None) or "self"
    facts = await adapter.compute(
        {
            "dob": payload.dob.isoformat(),
            "name_as_entered": payload.name_as_entered,
            "name_confirmed": payload.name_confirmed,
            "name_edited_latin": payload.name_edited_latin,
            "subject": subject,
            "chart_version": payload.chart_version,
        }
    )
    return NumerologyProfileResponse(facts=facts, confidence=confidence_for(facts))
