"""Chaldean / Pythagorean letter tables and the moolank / bhagyank maths.

Every expectation here is hand-computable from the published tables — these are
arithmetic tests, not divination. Cross-source parity for real names lives in
the 500-case hand-check harness (§5.5), where a human fills the values.
"""

from datetime import date

import pytest
from sitara_schemas import ErrorCode
from sitara_schemas.facts import MasterNumberPolicy, NumerologySystem

from sitara_astro.errors import AstroError
from sitara_astro.numerology.core import (
    bhagyank,
    letter_breakdown,
    moolank,
    name_number,
    reduce_number,
)
from sitara_astro.numerology.tables import CHALDEAN, PYTHAGOREAN


class TestChaldeanTable:
    def test_no_letter_is_ever_nine(self) -> None:
        """The defining property of Chaldean: 9 is sacred, never assigned."""
        assert 9 not in CHALDEAN.values()
        assert set(CHALDEAN.values()) == set(range(1, 9))

    def test_covers_the_whole_alphabet(self) -> None:
        assert set(CHALDEAN) == set("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

    @pytest.mark.parametrize(
        ("group", "value"),
        [
            ("AIJQY", 1),
            ("BKR", 2),
            ("CGLS", 3),
            ("DMT", 4),
            ("EHNX", 5),
            ("UVW", 6),
            ("OZ", 7),
            ("FP", 8),
        ],
    )
    def test_published_groups(self, group: str, value: int) -> None:
        for letter in group:
            assert CHALDEAN[letter] == value, letter


class TestPythagoreanTable:
    def test_is_a1z26_mod_nine(self) -> None:
        for index, letter in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
            assert PYTHAGOREAN[letter] == (index % 9) + 1

    def test_spot_values(self) -> None:
        assert PYTHAGOREAN["A"] == 1
        assert PYTHAGOREAN["I"] == 9
        assert PYTHAGOREAN["J"] == 1
        assert PYTHAGOREAN["R"] == 9
        assert PYTHAGOREAN["S"] == 1
        assert PYTHAGOREAN["Z"] == 8


class TestReduction:
    @pytest.mark.parametrize(
        ("number", "expected", "steps"),
        [
            (5, 5, (5,)),
            (10, 1, (10, 1)),
            (29, 2, (29, 11, 2)),
            (48, 3, (48, 12, 3)),
            (1999, 1, (1999, 28, 10, 1)),
        ],
    )
    def test_reduce_to_single_digit(self, number: int, expected: int, steps: tuple) -> None:
        value, trail = reduce_number(number, MasterNumberPolicy.REDUCE)
        assert value == expected
        assert trail == steps

    @pytest.mark.parametrize(("number", "expected"), [(29, 11), (22, 22), (6999, 33), (48, 3)])
    def test_preserve_policy_stops_at_master_numbers(self, number: int, expected: int) -> None:
        value, _ = reduce_number(number, MasterNumberPolicy.PRESERVE)
        assert value == expected

    def test_preserve_does_not_invent_masters_below_ten(self) -> None:
        assert reduce_number(9, MasterNumberPolicy.PRESERVE)[0] == 9

    def test_zero_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            reduce_number(0, MasterNumberPolicy.REDUCE)


class TestMoolank:
    @pytest.mark.parametrize(
        ("day", "expected"),
        [(1, 1), (9, 9), (10, 1), (15, 6), (19, 1), (28, 1), (29, 2), (31, 4)],
    )
    def test_birth_day_reduced(self, day: int, expected: int) -> None:
        value, _ = moolank(date(1990, 5, day), MasterNumberPolicy.REDUCE)
        assert value == expected

    def test_uses_day_only_not_month_or_year(self) -> None:
        a, _ = moolank(date(1990, 5, 15), MasterNumberPolicy.REDUCE)
        b, _ = moolank(date(2001, 12, 15), MasterNumberPolicy.REDUCE)
        assert a == b == 6

    def test_master_policy_applies(self) -> None:
        assert moolank(date(1990, 5, 29), MasterNumberPolicy.PRESERVE)[0] == 11


class TestBhagyank:
    def test_sums_every_digit_of_the_full_date(self) -> None:
        # 1990-05-15 → 1+9+9+0+0+5+1+5 = 30 → 3
        value, steps = bhagyank(date(1990, 5, 15), MasterNumberPolicy.REDUCE)
        assert steps[0] == 30
        assert value == 3

    @pytest.mark.parametrize(
        ("dob", "compound", "expected"),
        [
            (date(2000, 1, 1), 4, 4),  # 2+0+0+0+0+1+0+1 = 4
            (date(1985, 11, 2), 27, 9),  # 1+9+8+5+1+1+0+2 = 27 → 9
            (date(1996, 2, 29), 38, 2),  # 38 → 11 → 2
            (date(1990, 5, 15), 30, 3),  # 30 → 3
        ],
    )
    def test_known_dates(self, dob: date, compound: int, expected: int) -> None:
        value, steps = bhagyank(dob, MasterNumberPolicy.REDUCE)
        assert steps[0] == compound
        assert value == expected

    def test_leap_day_and_master_policy(self) -> None:
        assert bhagyank(date(1996, 2, 29), MasterNumberPolicy.PRESERVE)[0] == 11


class TestNameNumber:
    def test_chaldean_hand_computed(self) -> None:
        # LAKSHMI: L3 A1 K2 S3 H5 M4 I1 = 19 → 10 → 1
        value, compound, steps = name_number("Lakshmi", NumerologySystem.CHALDEAN,
                                             MasterNumberPolicy.REDUCE)
        assert compound == 19
        assert steps == (19, 10, 1)
        assert value == 1

    def test_pythagorean_hand_computed(self) -> None:
        # LAKSHMI: L3 A1 K2 S1 H8 M4 I9 = 28 → 10 → 1
        value, compound, _ = name_number("Lakshmi", NumerologySystem.PYTHAGOREAN,
                                         MasterNumberPolicy.REDUCE)
        assert compound == 28
        assert value == 1

    def test_systems_can_disagree(self) -> None:
        chaldean = name_number("Priya", NumerologySystem.CHALDEAN, MasterNumberPolicy.REDUCE)
        pythagorean = name_number("Priya", NumerologySystem.PYTHAGOREAN, MasterNumberPolicy.REDUCE)
        # P8 R2 I1 Y1 A1 = 13 vs P7 R9 I9 Y7 A1 = 33
        assert chaldean[1] == 13
        assert pythagorean[1] == 33

    def test_case_and_punctuation_insensitive(self) -> None:
        base = name_number("Lakshmi", NumerologySystem.CHALDEAN, MasterNumberPolicy.REDUCE)
        for variant in ("lakshmi", "LAKSHMI", "  Lakshmi  ", "Lak-shmi", "Lak'shmi"):
            assert name_number(variant, NumerologySystem.CHALDEAN,
                               MasterNumberPolicy.REDUCE) == base

    def test_spaces_do_not_change_the_sum(self) -> None:
        joined = name_number("RamaKumara", NumerologySystem.CHALDEAN, MasterNumberPolicy.REDUCE)
        spaced = name_number("Rama Kumara", NumerologySystem.CHALDEAN, MasterNumberPolicy.REDUCE)
        assert joined == spaced

    def test_non_latin_input_is_rejected(self) -> None:
        """The engine computes over Latin only — transliteration happens upstream
        and must be user-confirmed (§22.10)."""
        with pytest.raises(AstroError) as exc_info:
            name_number("लक्ष्मी", NumerologySystem.CHALDEAN, MasterNumberPolicy.REDUCE)
        assert exc_info.value.code is ErrorCode.ASTRO_NAME_INVALID

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(AstroError) as exc_info:
            name_number("   ", NumerologySystem.CHALDEAN, MasterNumberPolicy.REDUCE)
        assert exc_info.value.code is ErrorCode.ASTRO_NAME_INVALID

    def test_letter_breakdown_is_a_full_audit_trail(self) -> None:
        breakdown = letter_breakdown("Lakshmi", NumerologySystem.CHALDEAN)
        assert breakdown == (("L", 3), ("A", 1), ("K", 2), ("S", 3), ("H", 5), ("M", 4), ("I", 1))
        assert sum(v for _, v in breakdown) == 19
