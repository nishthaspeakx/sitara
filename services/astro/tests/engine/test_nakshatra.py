"""Nakshatra/pada arithmetic: 27 arcs of 13°20', four padas of 3°20' each."""

import pytest
from sitara_schemas.facts import Nakshatra

from sitara_astro.engine.nakshatra import fraction_traversed, nakshatra_pada

ARC = 360.0 / 27.0  # 13°20'
PADA = ARC / 4.0  # 3°20'


@pytest.mark.parametrize(
    ("longitude", "index", "name", "pada"),
    [
        (0.0, 1, Nakshatra.ASHWINI, 1),
        (PADA - 1e-9, 1, Nakshatra.ASHWINI, 1),
        (PADA, 1, Nakshatra.ASHWINI, 2),
        (ARC - 1e-9, 1, Nakshatra.ASHWINI, 4),
        (ARC, 2, Nakshatra.BHARANI, 1),
        (120.0, 10, Nakshatra.MAGHA, 1),  # 120° = start of Simha = Magha
        (359.999999, 27, Nakshatra.REVATI, 4),
        (26.0 * ARC, 27, Nakshatra.REVATI, 1),
    ],
)
def test_boundaries(longitude: float, index: int, name: Nakshatra, pada: int) -> None:
    actual_index, actual_name, actual_pada = nakshatra_pada(longitude)
    assert (actual_index, actual_name, actual_pada) == (index, name, pada)


def test_fraction_traversed() -> None:
    assert fraction_traversed(0.0) == 0.0
    assert fraction_traversed(ARC / 2) == pytest.approx(0.5)
    assert fraction_traversed(ARC) == 0.0  # start of Bharani
    assert fraction_traversed(ARC * 1.25) == pytest.approx(0.25)


def test_out_of_range_rejected() -> None:
    with pytest.raises(ValueError):
        nakshatra_pada(360.0)
    with pytest.raises(ValueError):
        nakshatra_pada(-0.001)
