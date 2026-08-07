"""Engine input types — shared by the API layer and the golden runner."""

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sitara_schemas.facts import BhavaSystem, DashaYearBasis, NodeType

GapPolicy = Literal["error", "shift_forward"]


class Place(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    tz: str  # IANA zone name — the only timezone authority (§5.2)


class BirthDetails(BaseModel):
    model_config = ConfigDict(frozen=True)

    date: dt.date
    time: dt.time
    fold: Literal[0, 1] | None = None  # disambiguates DST-fold wall times
    place: Place


class EngineOptions(BaseModel):
    """Every convention is explicit and lands in FactSnapshot.method, so the
    Jyotish reviewer can adjudicate defaults without archaeology."""

    model_config = ConfigDict(frozen=True)

    node_type: NodeType = NodeType.MEAN
    bhava_system: BhavaSystem = BhavaSystem.SRIPATI
    dasha_year: DashaYearBasis = DashaYearBasis.DAYS_365_25
    gap_policy: GapPolicy = "shift_forward"
