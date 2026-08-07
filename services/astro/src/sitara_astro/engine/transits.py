"""Gochar transits: graha positions at 00:00 UTC of a day, placed in the
natal chart's whole-sign houses and bhava spans."""

from dataclasses import dataclass
from datetime import UTC, date, datetime

from sitara_schemas.facts import RASHI_ORDER, Graha

from sitara_astro.engine.chart import NatalChart, bhava_of, rashi_of, whole_sign_house
from sitara_astro.engine.ephemeris import EclipticState, graha_longitudes
from sitara_astro.engine.inputs import EngineOptions


@dataclass(frozen=True)
class TransitPlacement:
    graha: Graha
    state: EclipticState
    whole_sign_house: int
    bhava: int


def compute_transits(
    natal: NatalChart, on_date: date, options: EngineOptions
) -> tuple[datetime, list[TransitPlacement]]:
    instant = datetime.combine(on_date, datetime.min.time(), tzinfo=UTC)
    states = graha_longitudes(instant, options.node_type)
    lagna_idx = RASHI_ORDER.index(natal.lagna_rashi)
    placements = [
        TransitPlacement(
            graha=graha,
            state=state,
            whole_sign_house=whole_sign_house(
                RASHI_ORDER.index(rashi_of(state.longitude_deg)), lagna_idx
            ),
            bhava=bhava_of(state.longitude_deg, natal.sandhi_deg),
        )
        for graha, state in states.items()
    ]
    return instant, placements
