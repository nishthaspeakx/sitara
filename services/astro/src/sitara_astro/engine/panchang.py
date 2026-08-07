"""Boundary instants for nakshatra and tithi (SPEC §5.5 ±2 min benchmark).

Scope note: this is pure Layer-A astronomy — the *instant* a longitude crosses
an edge, found by bisection on the same ephemeris that produces every other
fact. Panchang naming, regional month conventions, festivals and muhurats stay
Layer B behind PanchangProvider (§5.2); nothing here interprets a calendar.
"""

from datetime import datetime, timedelta

from sitara_schemas.facts import Graha, NodeType

from sitara_astro.engine.constants import NAKSHATRA_ARC_DEG
from sitara_astro.engine.ephemeris import graha_longitudes

TITHI_ARC_DEG = 12.0  # 30 tithis around the 360° Sun-Moon elongation
_SEARCH_LIMIT = timedelta(hours=32)  # longest nakshatra/tithi transit + headroom
_RESOLUTION = timedelta(seconds=1)  # §5.5 gate is ±2 min; we resolve 120× finer


def _moon_nakshatra_index(at: datetime, node_type: NodeType) -> int:
    lon = graha_longitudes(at, node_type)[Graha.MOON].longitude_deg
    return int(lon / NAKSHATRA_ARC_DEG)


def elongation_deg(at: datetime, node_type: NodeType) -> float:
    """Sun→Moon elongation in [0, 360). Ayanamsa cancels in the difference."""
    states = graha_longitudes(at, node_type)
    return (states[Graha.MOON].longitude_deg - states[Graha.SUN].longitude_deg) % 360.0


def tithi_index_of_elongation(elongation: float) -> int:
    """1..30 — 1 = Shukla Pratipada (just past new moon), 30 = Amavasya."""
    return int((elongation % 360.0) / TITHI_ARC_DEG) + 1


def tithi_index(at: datetime, node_type: NodeType) -> int:
    return tithi_index_of_elongation(elongation_deg(at, node_type))


def _first_change(at: datetime, node_type: NodeType, index_of) -> datetime:  # noqa: ANN001
    """Bisect for the first instant after `at` where `index_of` differs.

    Both indices advance monotonically over the search window (the Moon never
    retrogrades, and its elongation from the Sun always increases), so a single
    change-point exists and plain bisection converges on it.
    """
    start_index = index_of(at, node_type)
    lo, hi = at, at + _SEARCH_LIMIT
    if index_of(hi, node_type) == start_index:  # pragma: no cover - window is generous
        raise ValueError(f"no boundary within {_SEARCH_LIMIT} of {at.isoformat()}")
    while hi - lo > _RESOLUTION:
        mid = lo + (hi - lo) / 2
        if index_of(mid, node_type) == start_index:
            lo = mid
        else:
            hi = mid
    return hi.replace(microsecond=0)


def _last_change(at: datetime, node_type: NodeType, index_of) -> datetime:  # noqa: ANN001
    """Bisect for the instant the value running at `at` BEGAN.

    Mirror image of _first_change: the index is monotonic over the window, so
    the single change-point between "differs from now" and "equals now" is the
    start of the current tithi/nakshatra.
    """
    current = index_of(at, node_type)
    lo, hi = at - _SEARCH_LIMIT, at
    if index_of(lo, node_type) == current:  # pragma: no cover - window is generous
        raise ValueError(f"no boundary within {_SEARCH_LIMIT} before {at.isoformat()}")
    while hi - lo > _RESOLUTION:
        mid = lo + (hi - lo) / 2
        if index_of(mid, node_type) == current:
            hi = mid
        else:
            lo = mid
    return hi.replace(microsecond=0)


def next_nakshatra_boundary(at: datetime, node_type: NodeType) -> datetime:
    """Instant the Moon leaves the nakshatra it occupies at `at`."""
    return _first_change(at, node_type, _moon_nakshatra_index)


def next_tithi_boundary(at: datetime, node_type: NodeType) -> datetime:
    """Instant the tithi running at `at` ends."""
    return _first_change(at, node_type, tithi_index)


def tithi_window(at: datetime, node_type: NodeType) -> tuple[int, datetime, datetime]:
    """(tithi index, start, end) of the tithi running at `at`."""
    return (
        tithi_index(at, node_type),
        _last_change(at, node_type, tithi_index),
        _first_change(at, node_type, tithi_index),
    )


def nakshatra_window(at: datetime, node_type: NodeType) -> tuple[int, datetime, datetime]:
    """(nakshatra index 0-26, start, end) of the nakshatra the Moon occupies."""
    return (
        _moon_nakshatra_index(at, node_type),
        _last_change(at, node_type, _moon_nakshatra_index),
        _first_change(at, node_type, _moon_nakshatra_index),
    )
