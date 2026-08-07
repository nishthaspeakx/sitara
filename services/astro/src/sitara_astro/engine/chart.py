"""Natal chart assembly: whole-sign presentation + computed bhava (SPEC §5.2)."""

from collections.abc import Mapping
from dataclasses import dataclass

from sitara_schemas.facts import RASHI_ORDER, BhavaSystem, Graha, Rashi

from sitara_astro.engine.ephemeris import EclipticState, ascendant_and_cusps, graha_longitudes
from sitara_astro.engine.inputs import EngineOptions, Place
from sitara_astro.engine.tzresolve import ResolvedInstant


@dataclass(frozen=True)
class NatalChart:
    resolved: ResolvedInstant
    grahas: Mapping[Graha, EclipticState]
    lagna_deg: float
    madhya_deg: tuple[float, ...]
    sandhi_deg: tuple[float, ...]

    @property
    def lagna_rashi(self) -> Rashi:
        return rashi_of(self.lagna_deg)


def rashi_of(longitude_deg: float) -> Rashi:
    return RASHI_ORDER[min(int(longitude_deg // 30.0), 11)]


def whole_sign_house(graha_rashi_index: int, lagna_rashi_index: int) -> int:
    """House 1 = the lagna rashi itself; count forward through the zodiac."""
    return ((graha_rashi_index - lagna_rashi_index) % 12) + 1


def _midpoint(a: float, b: float) -> float:
    """Midpoint of the arc from a forward to b (shorter direction of travel)."""
    return (a + ((b - a) % 360.0) / 2.0) % 360.0


def sandhi_midpoints(madhya_deg: tuple[float, ...]) -> tuple[float, ...]:
    """Sripati sandhi: boundary i is the midpoint of madhya i and i+1 —
    sandhi_deg[i] is where house i+1 ends and house i+2 begins."""
    return tuple(_midpoint(madhya_deg[i], madhya_deg[(i + 1) % 12]) for i in range(12))


def bhava_of(longitude_deg: float, sandhi_deg: tuple[float, ...]) -> int:
    """House whose span [sandhi[i-1], sandhi[i]) contains the longitude."""
    for i in range(12):
        lo, hi = sandhi_deg[i - 1], sandhi_deg[i]
        if lo <= hi:
            if lo <= longitude_deg < hi:
                return i + 1
        elif longitude_deg >= lo or longitude_deg < hi:
            return i + 1
    raise ValueError(f"no bhava contains {longitude_deg}")  # pragma: no cover


def cusp_boundaries(madhya_deg: tuple[float, ...], system: BhavaSystem) -> tuple[float, ...]:
    """Boundary list in the sandhi_deg convention for the chosen system.

    Sripati treats cusps as house MIDDLES (sandhi = midpoints); the other
    systems treat cusps as house STARTS (boundary i = cusp of house i+2).
    """
    if system is BhavaSystem.SRIPATI:
        return sandhi_midpoints(madhya_deg)
    return tuple(madhya_deg[(i + 1) % 12] for i in range(12))


def compute_natal_chart(
    resolved: ResolvedInstant, place: Place, options: EngineOptions
) -> NatalChart:
    grahas = graha_longitudes(resolved.utc, options.node_type)
    lagna_deg, madhya = ascendant_and_cusps(
        resolved.utc, place.lat, place.lon, options.bhava_system
    )
    return NatalChart(
        resolved=resolved,
        grahas=grahas,
        lagna_deg=lagna_deg,
        madhya_deg=madhya,
        sandhi_deg=cusp_boundaries(madhya, options.bhava_system),
    )
