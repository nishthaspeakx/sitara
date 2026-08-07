"""The ONLY module allowed to import swisseph (global-state C library).

Every swe.* call happens under _SWE_LOCK; sidereal mode is re-asserted per
batch so Phase-2 selectable ayanamsas can never leak across requests. Endpoints
are sync `def` (FastAPI threadpool), so the lock serialises without blocking
the event loop.
"""

import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path

import swisseph as swe
from sitara_schemas.facts import BhavaSystem, EpheSource, Graha, NodeType

_SWE_LOCK = threading.Lock()
_EPHE_SOURCE: EpheSource = EpheSource.MOSHIER
_CALC_FLAG: int = swe.FLG_MOSEPH

# Planet files + moon files cover the nine grahas (nodes derive from MEAN/TRUE_NODE).
REQUIRED_EPHE_FILES = ("sepl_18.se1", "semo_18.se1")

_PLANET_IDS: dict[Graha, int] = {
    Graha.SUN: swe.SUN,
    Graha.MOON: swe.MOON,
    Graha.MARS: swe.MARS,
    Graha.MERCURY: swe.MERCURY,
    Graha.JUPITER: swe.JUPITER,
    Graha.VENUS: swe.VENUS,
    Graha.SATURN: swe.SATURN,
}

_HSYS: dict[BhavaSystem, bytes] = {
    BhavaSystem.SRIPATI: b"O",  # Porphyry cusps are the Sripati bhava-madhya
    BhavaSystem.PORPHYRY: b"O",
    BhavaSystem.EQUAL: b"A",
    BhavaSystem.PLACIDUS: b"P",
}


@dataclass(frozen=True)
class EclipticState:
    longitude_deg: float
    speed_deg_per_day: float


def init_ephemeris(data_path: Path | None) -> EpheSource:
    """Point swisseph at the Swiss data files if present; else Moshier.

    The chosen source is recorded in every fact's data_revision — a
    Moshier-computed fact is never claimed as file-grade (§5.2 D4).
    """
    global _EPHE_SOURCE, _CALC_FLAG
    with _SWE_LOCK:
        if data_path is not None and all((data_path / f).is_file() for f in REQUIRED_EPHE_FILES):
            swe.set_ephe_path(str(data_path))
            _EPHE_SOURCE, _CALC_FLAG = EpheSource.SWISS_FILES, swe.FLG_SWIEPH
        else:
            _EPHE_SOURCE, _CALC_FLAG = EpheSource.MOSHIER, swe.FLG_MOSEPH
    return _EPHE_SOURCE


def ephe_source() -> EpheSource:
    return _EPHE_SOURCE


def data_revision() -> str:
    """Pins every input that can silently change results (§5.2 D8)."""
    return f"swe={swe.version};ephe={_EPHE_SOURCE.value};tzdata={metadata.version('tzdata')}"





def _julian_day_ut(utc_dt: datetime) -> float:
    utc_dt = utc_dt.astimezone(UTC)
    hour = utc_dt.hour + utc_dt.minute / 60 + utc_dt.second / 3600 + utc_dt.microsecond / 3.6e9
    return swe.julday(utc_dt.year, utc_dt.month, utc_dt.day, hour, swe.GREG_CAL)


def graha_longitudes(utc_dt: datetime, node_type: NodeType) -> dict[Graha, EclipticState]:
    """Sidereal (Lahiri) longitudes + speeds for all nine grahas."""
    jd = _julian_day_ut(utc_dt)
    flags = _CALC_FLAG | swe.FLG_SIDEREAL | swe.FLG_SPEED
    node_id = swe.MEAN_NODE if node_type is NodeType.MEAN else swe.TRUE_NODE
    with _SWE_LOCK:
        swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
        states: dict[Graha, EclipticState] = {}
        for graha, planet_id in _PLANET_IDS.items():
            values, _ = swe.calc_ut(jd, planet_id, flags)
            states[graha] = EclipticState(
                longitude_deg=values[0] % 360.0, speed_deg_per_day=values[3]
            )
        rahu_values, _ = swe.calc_ut(jd, node_id, flags)
        states[Graha.RAHU] = EclipticState(
            longitude_deg=rahu_values[0] % 360.0, speed_deg_per_day=rahu_values[3]
        )
        states[Graha.KETU] = EclipticState(
            longitude_deg=(rahu_values[0] + 180.0) % 360.0, speed_deg_per_day=rahu_values[3]
        )
    return states


def ascendant_and_cusps(
    utc_dt: datetime, lat: float, lon: float, bhava_system: BhavaSystem
) -> tuple[float, tuple[float, ...]]:
    """Sidereal ascendant and the 12 cusps of the requested house system."""
    jd = _julian_day_ut(utc_dt)
    with _SWE_LOCK:
        swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
        cusps, ascmc = swe.houses_ex(jd, lat, lon, _HSYS[bhava_system], swe.FLG_SIDEREAL)
    return ascmc[0] % 360.0, tuple(c % 360.0 for c in cusps)
