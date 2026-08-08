"""Boundary-time computation — the ±2 min §5.5 threshold needs real crossings.

Pure Layer-A astronomy (root-finding on sidereal longitudes). Panchang NAMING,
festivals and regional calendars remain Layer B (§5.2) — this is only the
instant at which the Moon crosses a nakshatra edge or the Sun-Moon elongation
crosses a tithi edge.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sitara_schemas.facts import NodeType

from sitara_astro.config import Settings
from sitara_astro.engine.ephemeris import graha_longitudes, init_ephemeris
from sitara_astro.engine.nakshatra import nakshatra_pada
from sitara_astro.engine.panchang import (
    next_nakshatra_boundary,
    next_tithi_boundary,
    tithi_index,
)

init_ephemeris(Settings().resolved_swisseph_data_path)

AT = datetime(1990, 5, 15, 9, 0, tzinfo=UTC)
SECOND = timedelta(seconds=1)


class TestNakshatraBoundary:
    def test_index_changes_across_the_boundary(self) -> None:
        boundary = next_nakshatra_boundary(AT, NodeType.MEAN)
        before = _moon_nakshatra(boundary - SECOND)
        after = _moon_nakshatra(boundary + SECOND)
        assert before != after

    def test_boundary_is_ahead_and_within_a_nakshatra_transit(self) -> None:
        boundary = next_nakshatra_boundary(AT, NodeType.MEAN)
        assert boundary > AT
        # Moon crosses one nakshatra in ~24h; never more than ~28h.
        assert boundary - AT < timedelta(hours=28)

    def test_resolved_to_the_second(self) -> None:
        boundary = next_nakshatra_boundary(AT, NodeType.MEAN)
        assert boundary.microsecond == 0
        # Deterministic: recomputation lands on the same second.
        assert next_nakshatra_boundary(AT, NodeType.MEAN) == boundary

    def test_searching_from_just_before_a_boundary_finds_that_boundary(self) -> None:
        boundary = next_nakshatra_boundary(AT, NodeType.MEAN)
        again = next_nakshatra_boundary(boundary - timedelta(minutes=5), NodeType.MEAN)
        assert abs(again - boundary) <= timedelta(seconds=1)


class TestTithi:
    def test_index_in_range(self) -> None:
        assert 1 <= tithi_index(AT, NodeType.MEAN) <= 30

    def test_new_moon_is_tithi_one(self) -> None:
        """Elongation just past 0° is Shukla Pratipada."""
        assert tithi_index_from_elongation(0.5) == 1
        assert tithi_index_from_elongation(11.9) == 1
        assert tithi_index_from_elongation(12.1) == 2
        assert tithi_index_from_elongation(180.5) == 16  # Krishna Pratipada
        assert tithi_index_from_elongation(359.9) == 30  # Amavasya

    def test_boundary_changes_the_tithi(self) -> None:
        boundary = next_tithi_boundary(AT, NodeType.MEAN)
        assert tithi_index(boundary - SECOND, NodeType.MEAN) != tithi_index(
            boundary + SECOND, NodeType.MEAN
        )

    def test_boundary_within_one_tithi_span(self) -> None:
        boundary = next_tithi_boundary(AT, NodeType.MEAN)
        assert boundary > AT
        # A tithi runs ~19-26h; allow headroom.
        assert boundary - AT < timedelta(hours=30)


def tithi_index_from_elongation(elongation_deg: float) -> int:
    from sitara_astro.engine.panchang import tithi_index_of_elongation

    return tithi_index_of_elongation(elongation_deg)


def _moon_nakshatra(at: datetime) -> int:
    from sitara_schemas.facts import Graha

    lon = graha_longitudes(at, NodeType.MEAN)[Graha.MOON].longitude_deg
    return nakshatra_pada(lon)[0]


@pytest.mark.parametrize("hours", [0, 6, 13, 19])
def test_boundaries_are_monotonic_from_successive_starts(hours: int) -> None:
    start = AT + timedelta(hours=hours)
    assert next_nakshatra_boundary(start, NodeType.MEAN) > start
    assert next_tithi_boundary(start, NodeType.MEAN) > start
