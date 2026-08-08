"""Timezone resolution tests (SPEC §5.2: IANA tzdb is the sole tz authority).

These expectations ARE verifiable without a Jyotish reviewer — they are tzdb
facts, not astrology.
"""

from datetime import UTC, date, datetime, time

import pytest
from sitara_schemas import ErrorCode

from sitara_astro.engine.tzresolve import resolve_local
from sitara_astro.errors import AstroError


def test_plain_kolkata() -> None:
    resolved = resolve_local(date(1990, 5, 15), time(14, 30), "Asia/Kolkata")
    assert resolved.utc == datetime(1990, 5, 15, 9, 0, tzinfo=UTC)
    assert resolved.utc_offset_seconds == 19800
    assert resolved.fold_used == 0
    assert not resolved.ambiguous
    assert resolved.gap_shifted_minutes == 0


def test_ny_spring_forward_gap_shifts_60_min() -> None:
    resolved = resolve_local(date(2015, 3, 8), time(2, 30), "America/New_York")
    # 02:30 does not exist; shift_forward → 03:30 EDT (-04:00) → 07:30 UTC
    assert resolved.utc == datetime(2015, 3, 8, 7, 30, tzinfo=UTC)
    assert resolved.utc_offset_seconds == -4 * 3600
    assert resolved.gap_shifted_minutes == 60
    assert not resolved.ambiguous


def test_gap_with_error_policy_raises_insufficient_birth_data() -> None:
    with pytest.raises(AstroError) as exc_info:
        resolve_local(date(2015, 3, 8), time(2, 30), "America/New_York", gap_policy="error")
    assert exc_info.value.code is ErrorCode.ASTRO_INSUFFICIENT_BIRTH_DATA


def test_lord_howe_gap_is_30_minutes() -> None:
    resolved = resolve_local(date(2003, 10, 26), time(2, 15), "Australia/Lord_Howe")
    # 30-min DST zone: 02:15 + 30min = 02:45 at +11:00 → 2003-10-25 15:45 UTC
    assert resolved.gap_shifted_minutes == 30
    assert resolved.utc_offset_seconds == 11 * 3600
    assert resolved.utc == datetime(2003, 10, 25, 15, 45, tzinfo=UTC)


class TestFold:
    def test_first_occurrence(self) -> None:
        resolved = resolve_local(date(2015, 11, 1), time(1, 30), "America/New_York", fold=0)
        assert resolved.utc_offset_seconds == -4 * 3600  # EDT
        assert resolved.ambiguous
        assert resolved.fold_used == 0
        assert resolved.utc == datetime(2015, 11, 1, 5, 30, tzinfo=UTC)

    def test_second_occurrence(self) -> None:
        resolved = resolve_local(date(2015, 11, 1), time(1, 30), "America/New_York", fold=1)
        assert resolved.utc_offset_seconds == -5 * 3600  # EST
        assert resolved.ambiguous
        assert resolved.fold_used == 1
        assert resolved.utc == datetime(2015, 11, 1, 6, 30, tzinfo=UTC)

    def test_unspecified_fold_defaults_to_first_and_flags_ambiguity(self) -> None:
        resolved = resolve_local(date(2015, 11, 1), time(1, 30), "America/New_York")
        assert resolved.fold_used == 0
        assert resolved.ambiguous
        assert resolved.utc_offset_seconds == -4 * 3600

    def test_unambiguous_time_not_flagged(self) -> None:
        resolved = resolve_local(date(2015, 11, 1), time(12, 0), "America/New_York")
        assert not resolved.ambiguous
        assert resolved.utc_offset_seconds == -5 * 3600


class TestHistoricalOffsets:
    @pytest.mark.parametrize(
        ("d", "t", "tz", "offset_seconds"),
        [
            (date(1943, 6, 10), time(12, 0), "Asia/Kolkata", 23400),  # war time +06:30
            (date(1944, 7, 4), time(15, 0), "Europe/London", 7200),  # double summer time
            (date(1974, 1, 6), time(10, 0), "America/New_York", -14400),  # EDT in January
            (date(1980, 7, 10), time(9, 20), "Asia/Kathmandu", 19800),  # Nepal pre-1986
            (date(1990, 4, 12), time(6, 0), "Asia/Kathmandu", 20700),  # Nepal +05:45
            (date(1996, 7, 1), time(8, 30), "Asia/Colombo", 23400),  # Sri Lanka 1996
        ],
    )
    def test_offset(self, d: date, t: time, tz: str, offset_seconds: int) -> None:
        assert resolve_local(d, t, tz).utc_offset_seconds == offset_seconds


def test_unknown_zone_raises_place_unresolved() -> None:
    with pytest.raises(AstroError) as exc_info:
        resolve_local(date(1990, 5, 15), time(14, 30), "Asia/Atlantis")
    assert exc_info.value.code is ErrorCode.ASTRO_PLACE_UNRESOLVED


def test_pinned_tzdata_package_is_the_only_source() -> None:
    """§5.2 D8: data_revision records tzdata==<ver>, so the host OS tzdb must
    never answer lookups — importing tzresolve empties zoneinfo's TZPATH."""
    import zoneinfo

    assert zoneinfo.TZPATH == ()
    # With TZPATH empty, a successful load can only have come from the pinned
    # tzdata wheel — the host OS tzdb is unreachable.
    resolved = resolve_local(date(1990, 5, 15), time(14, 30), "Asia/Kolkata")
    assert resolved.utc_offset_seconds == 19800
