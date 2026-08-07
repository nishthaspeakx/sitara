"""Vimshottari dasha — pure arithmetic from the Moon's sidereal longitude.

All period boundaries are expressed as a single offset-in-years from the cycle
anchor and converted to a datetime exactly once, so adjacent periods share
byte-identical boundaries (no float drift between maha/antar/pratyantar).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sitara_schemas.facts import DashaLevel, DashaYearBasis, Graha

from sitara_astro.engine.constants import (
    DASHA_CYCLE_YEARS,
    DASHA_LORD_SEQUENCE,
    DASHA_YEARS,
    YEAR_DAYS,
)
from sitara_astro.engine.nakshatra import fraction_traversed, nakshatra_pada


@dataclass(frozen=True)
class DashaPeriod:
    level: DashaLevel
    lord: Graha
    start: datetime
    end: datetime
    parents: tuple[Graha, ...]


def compute_vimshottari(
    moon_longitude_deg: float,
    birth_utc: datetime,
    year_basis: DashaYearBasis = DashaYearBasis.DAYS_365_25,
    levels: int = 3,
) -> list[DashaPeriod]:
    """Full 120-year cycle from the maha running at birth, to the given depth."""
    year_days = YEAR_DAYS[year_basis]
    nak_index, _, _ = nakshatra_pada(moon_longitude_deg)
    first_lord_pos = (nak_index - 1) % 9
    elapsed_years = DASHA_YEARS[DASHA_LORD_SEQUENCE[first_lord_pos]] * fraction_traversed(
        moon_longitude_deg
    )

    def at(years_from_cycle_start: float) -> datetime:
        return birth_utc + timedelta(days=(years_from_cycle_start - elapsed_years) * year_days)

    periods: list[DashaPeriod] = []
    cursor = 0  # integer years since cycle start — exact
    for i in range(9):
        maha_lord = DASHA_LORD_SEQUENCE[(first_lord_pos + i) % 9]
        maha_years = DASHA_YEARS[maha_lord]
        periods.append(
            DashaPeriod(
                level=DashaLevel.MAHA,
                lord=maha_lord,
                start=at(cursor),
                end=at(cursor + maha_years),
                parents=(),
            )
        )
        if levels >= 2:
            periods.extend(
                _subperiods(at, cursor, maha_years, maha_lord, levels)
            )
        cursor += maha_years
    return periods


def _subperiods(
    at,  # noqa: ANN001 - closure over the cycle anchor
    maha_start_years: int,
    maha_years: int,
    maha_lord: Graha,
    levels: int,
) -> list[DashaPeriod]:
    periods: list[DashaPeriod] = []
    antar_seq_start = DASHA_LORD_SEQUENCE.index(maha_lord)
    cum = 0  # integer "lord-years" consumed within this maha — exact
    for j in range(9):
        antar_lord = DASHA_LORD_SEQUENCE[(antar_seq_start + j) % 9]
        antar_years = DASHA_YEARS[antar_lord]
        start_frac = cum / DASHA_CYCLE_YEARS
        end_frac = (cum + antar_years) / DASHA_CYCLE_YEARS
        periods.append(
            DashaPeriod(
                level=DashaLevel.ANTAR,
                lord=antar_lord,
                start=at(maha_start_years + maha_years * start_frac),
                end=at(maha_start_years + maha_years * end_frac),
                parents=(maha_lord,),
            )
        )
        if levels >= 3:
            antar_span_years = maha_years * antar_years / DASHA_CYCLE_YEARS
            antar_start_years = maha_start_years + maha_years * start_frac
            praty_seq_start = DASHA_LORD_SEQUENCE.index(antar_lord)
            praty_cum = 0
            for k in range(9):
                praty_lord = DASHA_LORD_SEQUENCE[(praty_seq_start + k) % 9]
                praty_years = DASHA_YEARS[praty_lord]
                periods.append(
                    DashaPeriod(
                        level=DashaLevel.PRATYANTAR,
                        lord=praty_lord,
                        start=at(
                            antar_start_years
                            + antar_span_years * (praty_cum / DASHA_CYCLE_YEARS)
                        ),
                        end=at(
                            antar_start_years
                            + antar_span_years * ((praty_cum + praty_years) / DASHA_CYCLE_YEARS)
                        ),
                        parents=(maha_lord, antar_lord),
                    )
                )
                praty_cum += praty_years
        cum += antar_years
    return periods
