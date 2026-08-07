"""Chart assembly maths that needs no ephemeris: whole-sign counting and
Sripati sandhi construction (midpoints on the shorter arc, mod 360)."""

import pytest

from sitara_astro.engine.chart import bhava_of, sandhi_midpoints, whole_sign_house


class TestWholeSign:
    @pytest.mark.parametrize(
        ("graha_rashi", "lagna_rashi", "house"),
        [
            (0, 0, 1),
            (1, 0, 2),
            (0, 1, 12),  # wrap backwards
            (11, 0, 12),
            (6, 6, 1),
            (5, 6, 12),
        ],
    )
    def test_counting(self, graha_rashi: int, lagna_rashi: int, house: int) -> None:
        assert whole_sign_house(graha_rashi, lagna_rashi) == house


class TestSripati:
    def test_even_cusps_give_offset_midpoints(self) -> None:
        madhya = tuple(float(i * 30) for i in range(12))
        sandhi = sandhi_midpoints(madhya)
        assert sandhi == tuple(float(i * 30 + 15) for i in range(12))

    def test_midpoint_wraps_shorter_arc(self) -> None:
        # midpoint of 350° and 10° is 0°, never 180°
        madhya = (350.0, 10.0) + tuple(float(30 + i * 30) for i in range(10))
        sandhi = sandhi_midpoints(madhya)
        assert sandhi[0] == pytest.approx(0.0)

    def test_bhava_assignment(self) -> None:
        madhya = tuple(float(i * 30) for i in range(12))
        sandhi = sandhi_midpoints(madhya)  # boundaries at 15, 45, ...
        assert bhava_of(0.0, sandhi) == 1
        assert bhava_of(14.999, sandhi) == 1
        assert bhava_of(15.0, sandhi) == 2  # boundary starts the next bhava
        assert bhava_of(44.999, sandhi) == 2
        assert bhava_of(350.0, sandhi) == 1  # wrap: house 1 spans 345°..15°
