"""Closed astronomical constants for the Layer-A engine."""

from sitara_schemas.facts import DashaYearBasis, Graha

NAKSHATRA_ARC_DEG = 360.0 / 27.0  # 13°20'
PADA_ARC_DEG = NAKSHATRA_ARC_DEG / 4.0  # 3°20'

# Vimshottari lord cycle starting at Ashwini; nakshatra i (1-based) → lord (i-1) % 9.
DASHA_LORD_SEQUENCE: tuple[Graha, ...] = (
    Graha.KETU,
    Graha.VENUS,
    Graha.SUN,
    Graha.MOON,
    Graha.MARS,
    Graha.RAHU,
    Graha.JUPITER,
    Graha.SATURN,
    Graha.MERCURY,
)

DASHA_YEARS: dict[Graha, int] = {
    Graha.KETU: 7,
    Graha.VENUS: 20,
    Graha.SUN: 6,
    Graha.MOON: 10,
    Graha.MARS: 7,
    Graha.RAHU: 18,
    Graha.JUPITER: 16,
    Graha.SATURN: 19,
    Graha.MERCURY: 17,
}

DASHA_CYCLE_YEARS = 120  # sum of DASHA_YEARS values

YEAR_DAYS: dict[DashaYearBasis, float] = {
    DashaYearBasis.DAYS_365_25: 365.25,
    DashaYearBasis.SIDEREAL_365_2564: 365.2564,
    DashaYearBasis.SAVANA_360: 360.0,
}
