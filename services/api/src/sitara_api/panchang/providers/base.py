"""The one PanchangProvider interface (SPEC §5.2 Layer B).

DivineAPI (primary) and Prokerala (cross-check oracle) sit behind this, and
nothing above it knows which vendor answered. Two rules make that real:

1. Adapters return NORMALISED types, never vendor JSON. The Layer-D comparison
   job can only diff two sources if they speak one vocabulary, and a vendor's
   English label must never reach a user (§2.4).
2. Adapters raise the §34.4 envelope's error codes, never an upstream body.
"""

import datetime as dt
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field
from sitara_schemas.facts import (
    Choghadiya,
    DayTimingKind,
    MuhuratType,
    TimingQuality,
    Tradition,
)


class ProviderName(StrEnum):
    """§5.2: DivineAPI primary, Prokerala cross-check. LAYER_A is not a
    provider — it is our own engine, and it is named in FactSource instead."""

    DIVINEAPI = "divineapi"
    PROKERALA = "prokerala"


class ResolvedPlace(BaseModel):
    """An explicit place: coordinates, IANA zone, and the label to show.

    §30.2 requires every timing to be computed for a stated place and labelled
    with its city. Carrying the label alongside the coordinates makes that
    structural rather than a convention someone remembers to follow.
    """

    model_config = ConfigDict(frozen=True)

    label: str = Field(min_length=1, max_length=120)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    tz: str = Field(min_length=1)


class PanchangQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    local_date: dt.date
    place: ResolvedPlace
    tradition: Tradition = Tradition.AMANTA


class MuhuratQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    muhurat_type: MuhuratType
    date_from: dt.date
    date_to: dt.date
    place: ResolvedPlace
    tradition: Tradition = Tradition.AMANTA


class BoundaryReading(BaseModel):
    """One source's opinion about when a tithi or nakshatra begins and ends.

    This is the quantity §5.2 Layer D compares at a 2-minute tolerance.
    """

    model_config = ConfigDict(frozen=True)

    index: int = Field(ge=1)
    starts_utc: dt.datetime
    ends_utc: dt.datetime


class TimingWindow(BaseModel):
    model_config = ConfigDict(frozen=True)

    timing: DayTimingKind
    starts_utc: dt.datetime
    ends_utc: dt.datetime
    quality: TimingQuality
    choghadiya: Choghadiya | None = None
    part_index: int | None = Field(default=None, ge=1, le=8)


class MuhuratWindow(BaseModel):
    model_config = ConfigDict(frozen=True)

    starts_utc: dt.datetime
    ends_utc: dt.datetime
    quality: TimingQuality


class NormalisedPanchang(BaseModel):
    """The comparable core of a panchang day, in one vocabulary."""

    model_config = ConfigDict(frozen=True)

    provider: ProviderName
    local_date: dt.date
    sunrise_utc: dt.datetime
    sunset_utc: dt.datetime
    tithi: BoundaryReading
    nakshatra: BoundaryReading


class NormalisedDayTimings(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: ProviderName
    local_date: dt.date
    windows: tuple[TimingWindow, ...]


class NormalisedMuhurat(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: ProviderName
    muhurat_type: MuhuratType
    windows: tuple[MuhuratWindow, ...]


class PanchangProvider(Protocol):
    """Both vendors implement exactly this. Adding a third (§5.2 names
    AstrologyAPI and VedicAstroAPI as evaluated alternatives) means writing one
    adapter, not touching anything above."""

    name: ProviderName

    async def panchang(self, query: PanchangQuery) -> NormalisedPanchang: ...

    async def day_timings(self, query: PanchangQuery) -> NormalisedDayTimings: ...

    async def muhurat(self, query: MuhuratQuery) -> NormalisedMuhurat: ...
