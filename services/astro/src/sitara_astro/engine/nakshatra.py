"""Nakshatra/pada arithmetic on sidereal longitudes."""

from sitara_schemas.facts import NAKSHATRA_ORDER, Nakshatra


def nakshatra_pada(longitude_deg: float) -> tuple[int, Nakshatra, int]:
    """Return (1-based index, nakshatra, pada 1-4) for a sidereal longitude."""
    if not 0.0 <= longitude_deg < 360.0:
        raise ValueError(f"longitude out of range [0, 360): {longitude_deg}")
    position = longitude_deg * 27.0 / 360.0  # nakshatra units
    index = min(int(position), 26)
    within = position - index
    pada = min(int(within * 4.0), 3) + 1
    return index + 1, NAKSHATRA_ORDER[index], pada


def fraction_traversed(longitude_deg: float) -> float:
    """Fraction of the occupied nakshatra already crossed (0 ≤ f < 1)."""
    position = longitude_deg * 27.0 / 360.0
    return position - int(position)
