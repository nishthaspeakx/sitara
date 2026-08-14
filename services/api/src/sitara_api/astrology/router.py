"""The chart endpoint (CC-007's `KundliChart`, §5.3, §5.4).

Until M10 nothing served natal facts to a client: `app.py` mounted auth,
numerology, panchang, chat, calls, voice, memory, onboarding and today, and a
chart reached the user only inside a brief or a turn. The diagram needs the
placements themselves.

**What crosses the wire is deliberately narrow.** Twelve houses, their rashis,
which grahas sit in each, the lagna, and a §5.4 confidence state — everything
a diamond needs and nothing more. No longitudes, no fact ids (§30.4 keeps
those internal), no birth details. A renderer that received degrees would
eventually compute something with them, and §5.3 says the only thing that
computes is the engine.
"""

from __future__ import annotations

from bson import ObjectId
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field
from sitara_schemas import ErrorCode
from sitara_schemas.facts import ConfidenceState, Graha, Rashi

from sitara_api.astrology.chart_adapter import (
    ChartEngineUnavailable,
    InsufficientBirthData,
)
from sitara_api.astrology.kundli import Kundli, build_kundli, build_moon_chart
from sitara_api.auth.router import CurrentSession
from sitara_api.errors import ApiError

router = APIRouter(prefix="/v1/chart", tags=["astrology"])


class HouseView(BaseModel):
    house: int = Field(ge=1, le=12)
    rashi: Rashi
    grahas: list[Graha]
    is_lagna: bool = False


class ChartView(BaseModel):
    houses: list[HouseView]
    lagna_rashi: Rashi
    #: §5.4, and it is on the ARTEFACT rather than beside it (CC-007): a
    #: diamond drawn from a guessed ascendant is a confident-looking lie, so
    #: the chart carries its own honesty.
    confidence: ConfidenceState
    #: True in Moon-chart mode — the first house is chandra lagna, not the
    #: ascendant, and the client must say so rather than draw an ordinary
    #: kundli with a quieter label.
    moon_chart: bool = False
    #: Grahas the engine placed nowhere. Empty on a complete natal set; served
    #: so a chart missing one says so instead of drawing eight as nine.
    unplaced: list[Graha] = Field(default_factory=list)

    @classmethod
    def of(
        cls, kundli: Kundli, *, confidence: ConfidenceState, moon_chart: bool
    ) -> ChartView:
        return cls(
            houses=[
                HouseView(
                    house=h.house,
                    rashi=h.rashi,
                    grahas=list(h.grahas),
                    is_lagna=h.is_lagna,
                )
                for h in kundli.houses
            ],
            lagna_rashi=kundli.lagna_rashi,
            confidence=confidence,
            moon_chart=moon_chart,
            unplaced=list(kundli.unplaced),
        )


def _facade(request: Request):  # noqa: ANN202
    facade = getattr(request.app.state, "astrology", None)
    if facade is None:
        raise ApiError(ErrorCode.SYS_UNAVAILABLE, "errors.sys.unavailable")
    return facade


def _confidence_for(time_accuracy: str, *, moon_chart: bool) -> ConfidenceState:
    """§5.4's states, from the birth time's accuracy.

    `unknown` and `part_of_day` both mean there is no ascendant to count from,
    so both land in Moon-chart mode — and §5.4 calls that
    `tradition_based_general` rather than `approximate`, because it is not a
    slightly-fuzzy version of the right chart; it is a different chart.
    """
    if moon_chart:
        return ConfidenceState.TRADITION_BASED_GENERAL
    if time_accuracy == "approximate":
        return ConfidenceState.APPROXIMATE
    return ConfidenceState.VERIFIED


@router.get("", response_model=ChartView)
async def get_chart(
    request: Request,
    session: CurrentSession,
    local_date: str = Query(alias="local_date"),
    timezone: str = "Asia/Kolkata",
    subject_id: str | None = Query(default=None),
) -> ChartView:
    """The natal chart as twelve houses (S28, and the user's own profile).

    `subject_id` names a family member; omitted, it is the account-holder's
    own chart. §30.5 keeps family guidance in the account-holder's spaces, and
    the facade is scoped to her — a member id that is not hers resolves to no
    birth details rather than to somebody else's chart.
    """
    facade = _facade(request)
    subject = subject_id or str(session[0])
    if subject_id is not None:
        member = await _owned_member(request, session[0], subject_id)
        if member is None:
            raise ApiError(ErrorCode.SYS_VALIDATION, "errors.family.not_found")

    try:
        bundle = await facade.chart_for(
            subject, local_date=local_date, timezone=timezone, include_transits=False
        )
    except InsufficientBirthData:
        # §5.3: the engine declines rather than guessing, and so does this.
        # §28.2 has a designed variant for the missing-birth-details case;
        # a chart nobody can compute is that variant's business, not a 500.
        raise ApiError(
            ErrorCode.ASTRO_INSUFFICIENT_BIRTH_DATA, "errors.astro.insufficient_birth_data"
        ) from None
    except ChartEngineUnavailable:
        raise ApiError(ErrorCode.SYS_UNAVAILABLE, "errors.sys.unavailable") from None

    time_accuracy = await _time_accuracy(request, subject)
    kundli = build_kundli(bundle.natal)
    moon_chart = kundli is None
    if kundli is None:
        kundli = build_moon_chart(bundle.natal)
    if kundli is None:
        # No lagna AND no Moon — there is no chart to draw and none will be
        # invented (§5.3).
        raise ApiError(
            ErrorCode.ASTRO_INSUFFICIENT_BIRTH_DATA, "errors.astro.insufficient_birth_data"
        )

    return ChartView.of(
        kundli,
        confidence=_confidence_for(time_accuracy, moon_chart=moon_chart),
        moon_chart=moon_chart,
    )


async def _owned_member(request: Request, owner_user_id: ObjectId, member_id: str):  # noqa: ANN202
    service = getattr(request.app.state, "family_service", None)
    if service is None:
        raise ApiError(ErrorCode.SYS_UNAVAILABLE, "errors.sys.unavailable")
    try:
        oid = ObjectId(member_id)
    except Exception:
        raise ApiError(ErrorCode.SYS_VALIDATION) from None
    return await service.get(owner_user_id, oid)


async def _time_accuracy(request: Request, subject: str) -> str:
    """The STORED accuracy, from the facade's own accessor.

    Never read off `BirthInput`, which is narrowed to the five fields the
    engine needs and carries no accuracy at all — a `getattr` against it would
    return a default for every user and quietly label every approximate chart
    `verified`. §30.2 stores a window for an approximate time, so the presence
    of a time proves nothing.
    """
    return await _facade(request).time_accuracy(subject)


__all__ = ["ChartView", "HouseView", "router"]
