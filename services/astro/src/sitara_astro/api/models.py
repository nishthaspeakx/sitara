"""Request/response models for the facts endpoints."""

import datetime as dt

from pydantic import BaseModel, Field
from sitara_schemas.facts import FactSnapshot, Tradition

from sitara_astro.engine.inputs import BirthDetails, EngineOptions, Place
from sitara_astro.numerology.inputs import NumerologyOptions


class FactsRequest(BaseModel):
    birth: BirthDetails
    options: EngineOptions = EngineOptions()
    subject: str = Field(pattern=r"^[A-Za-z0-9_-]+$", max_length=64)
    chart_version: int = Field(ge=1)


class TransitsRequest(FactsRequest):
    transit_date_utc: dt.date


class FactsResponse(BaseModel):
    facts: list[FactSnapshot]


class PanchangRequest(BaseModel):
    """Layer-A panchang for a LOCAL date at an explicit place (§30.2).

    There is no `subject`: panchang facts are global, keyed by place+tradition
    (§7.2/§34.2), and a user id must never reach this endpoint.
    """

    local_date: dt.date
    place: Place
    tradition: Tradition = Tradition.AMANTA
    options: EngineOptions = EngineOptions()
    chart_version: int = Field(default=1, ge=1)
    include_day_timings: bool = True


class NumerologyRequest(BaseModel):
    """§22.10: `name_as_entered` is what the user typed; `name_confirmed` is
    their explicit yes to the proposal; `name_edited_latin` is their override.
    Moolank/bhagyank need only `dob`, so the §10-9 reveal works with no name.
    """

    dob: dt.date
    name_as_entered: str | None = Field(default=None, max_length=200)
    name_confirmed: bool = False
    name_edited_latin: str | None = Field(default=None, max_length=200)
    options: NumerologyOptions = NumerologyOptions()
    subject: str = Field(pattern=r"^[A-Za-z0-9_-]+$", max_length=64)
    chart_version: int = Field(ge=1)


class TransliterationProposalResponse(BaseModel):
    """Returned when a non-Latin name still needs the §22.10 confirmation."""

    script: str
    iso15919: str | None
    suggested_latin: str
    scheme: str | None
    confirmation_message_key: str
    confirmation_params: dict[str, str]
