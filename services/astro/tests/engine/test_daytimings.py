"""Sunrise-anchored day divisions — rahu kaal, yamaganda, gulikai, abhijit,
choghadiya (SPEC §5.2 Layer B fallback scope).

SCOPE NOTE (§32.2 / decision D1): these are *tradition rule tables*, not
astronomy. DivineAPI is primary for the served value; this module exists so the
§8 ladder has a real internal rung and so the Layer-D job has an independent
third opinion. The arithmetic below is deterministic and testable; the RULE
TABLES themselves are Jyotish-adjudicable and carried in golden-set.
"""

from datetime import date, timedelta

import pytest
from sitara_schemas.facts import Choghadiya, DayTimingKind, TimingQuality

from sitara_astro.engine.daytimings import CHOGHADIYA_CYCLE, day_timings
from sitara_astro.engine.inputs import Place
from sitara_astro.engine.riseset import sun_day

MUMBAI = Place(name="Mumbai", lat=19.0760, lon=72.8777, tz="Asia/Kolkata")

# 2026-08-07 is a Friday; the surrounding week gives one of each weekday.
WEEK = {
    "sunday": date(2026, 8, 9),
    "monday": date(2026, 8, 10),
    "tuesday": date(2026, 8, 11),
    "wednesday": date(2026, 8, 12),
    "thursday": date(2026, 8, 13),
    "friday": date(2026, 8, 7),
    "saturday": date(2026, 8, 8),
}


def timings_for(day_name: str):
    d = WEEK[day_name]
    return d, day_timings(d, MUMBAI)


def only(timings, kind: DayTimingKind):
    matches = [t for t in timings if t.timing is kind]
    assert len(matches) == 1, f"expected exactly one {kind}, got {len(matches)}"
    return matches[0]


def of_kind(timings, kind: DayTimingKind):
    return [t for t in timings if t.timing is kind]


def _name(part) -> str:  # noqa: ANN001
    """Choghadiya parts always carry a name — the model enforces it."""
    assert part.choghadiya is not None
    return part.choghadiya.value


def assert_same_instant(actual, expected) -> None:
    """These assertions are about WHICH eighth of the day a band occupies, not
    about microsecond arithmetic; a second of slack keeps them honest without
    pinning float division. Exactness where it matters — that adjacent windows
    share an endpoint — is asserted separately in TestDayDivision."""
    assert abs((actual - expected).total_seconds()) < 1


class TestDayDivision:
    def test_eight_day_parts_tile_sunrise_to_sunset(self) -> None:
        """No gap, no overlap, no lost second — a user reading two adjacent
        windows must never see a hole between them."""
        d, timings = timings_for("friday")
        day = sun_day(d, MUMBAI)
        parts = sorted(of_kind(timings, DayTimingKind.CHOGHADIYA_DAY), key=lambda t: t.starts_utc)
        assert len(parts) == 8
        assert parts[0].starts_utc == day.sunrise
        assert parts[-1].ends_utc == day.sunset
        for earlier, later in zip(parts, parts[1:], strict=False):
            assert earlier.ends_utc == later.starts_utc

    def test_night_parts_run_sunset_to_next_sunrise(self) -> None:
        d, timings = timings_for("friday")
        day = sun_day(d, MUMBAI)
        parts = sorted(of_kind(timings, DayTimingKind.CHOGHADIYA_NIGHT), key=lambda t: t.starts_utc)
        assert len(parts) == 8
        assert parts[0].starts_utc == day.sunset
        assert parts[-1].ends_utc == day.next_sunrise

    def test_parts_are_equal_length(self) -> None:
        """Equal to the microsecond is impossible AND undesirable: a day length
        rarely divides by eight exactly, so insisting on identical parts would
        reintroduce the gaps the tiling test forbids. The partition absorbs the
        remainder — parts may differ by at most one microsecond."""
        _, timings = timings_for("friday")
        lengths = [
            (t.ends_utc - t.starts_utc) for t in of_kind(timings, DayTimingKind.CHOGHADIYA_DAY)
        ]
        assert max(lengths) - min(lengths) <= timedelta(microseconds=1)


class TestRahuKaalTable:
    """The published weekday→part table (Drik Panchang convention).
    Part numbers are 1-indexed over the eight equal day parts."""

    EXPECTED = {
        "sunday": 8,
        "monday": 2,
        "tuesday": 7,
        "wednesday": 5,
        "thursday": 6,
        "friday": 4,
        "saturday": 3,
    }

    @pytest.mark.parametrize("day_name", list(EXPECTED))
    def test_rahu_kaal_lands_on_the_published_part(self, day_name: str) -> None:
        d, timings = timings_for(day_name)
        day = sun_day(d, MUMBAI)
        part = (day.sunset - day.sunrise) / 8
        rahu = only(timings, DayTimingKind.RAHU_KAAL)
        expected_start = day.sunrise + part * (self.EXPECTED[day_name] - 1)
        assert_same_instant(rahu.starts_utc, expected_start)
        assert_same_instant(rahu.ends_utc, expected_start + part)

    def test_rahu_kaal_is_never_framed_as_auspicious(self) -> None:
        _, timings = timings_for("friday")
        assert only(timings, DayTimingKind.RAHU_KAAL).quality is TimingQuality.INAUSPICIOUS


class TestOtherBands:
    YAMAGANDA = {
        "sunday": 5,
        "monday": 4,
        "tuesday": 3,
        "wednesday": 2,
        "thursday": 1,
        "friday": 7,
        "saturday": 6,
    }
    GULIKAI = {
        "sunday": 7,
        "monday": 6,
        "tuesday": 5,
        "wednesday": 4,
        "thursday": 3,
        "friday": 2,
        "saturday": 1,
    }

    @pytest.mark.parametrize("day_name", list(YAMAGANDA))
    def test_yamaganda_table(self, day_name: str) -> None:
        d, timings = timings_for(day_name)
        day = sun_day(d, MUMBAI)
        part = (day.sunset - day.sunrise) / 8
        band = only(timings, DayTimingKind.YAMAGANDA)
        assert_same_instant(band.starts_utc, day.sunrise + part * (self.YAMAGANDA[day_name] - 1))

    @pytest.mark.parametrize("day_name", list(GULIKAI))
    def test_gulikai_table(self, day_name: str) -> None:
        d, timings = timings_for(day_name)
        day = sun_day(d, MUMBAI)
        part = (day.sunset - day.sunrise) / 8
        band = only(timings, DayTimingKind.GULIKAI)
        assert_same_instant(band.starts_utc, day.sunrise + part * (self.GULIKAI[day_name] - 1))

    def test_the_three_bands_never_coincide(self) -> None:
        for day_name in WEEK:
            _, timings = timings_for(day_name)
            starts = {
                only(timings, k).starts_utc
                for k in (
                    DayTimingKind.RAHU_KAAL,
                    DayTimingKind.YAMAGANDA,
                    DayTimingKind.GULIKAI,
                )
            }
            assert len(starts) == 3, f"{day_name}: bands collided"

    def test_abhijit_is_centred_on_solar_noon(self) -> None:
        """The 8th of fifteen muhurtas — day_length/15 wide, straddling noon."""
        d, timings = timings_for("friday")
        day = sun_day(d, MUMBAI)
        abhijit = only(timings, DayTimingKind.ABHIJIT)
        width = (day.sunset - day.sunrise) / 15
        centre = abhijit.starts_utc + (abhijit.ends_utc - abhijit.starts_utc) / 2
        assert abs((centre - day.solar_noon).total_seconds()) < 5 * 60
        assert abs((abhijit.ends_utc - abhijit.starts_utc) - width) < timedelta(seconds=1)

    def test_abhijit_is_the_one_auspicious_band(self) -> None:
        _, timings = timings_for("friday")
        assert only(timings, DayTimingKind.ABHIJIT).quality is TimingQuality.AUSPICIOUS


class TestChoghadiyaSequence:
    """The seven-name cycle repeats; only the weekday's entry point changes."""

    DAY_START = {
        "sunday": Choghadiya.UDVEG,
        "monday": Choghadiya.AMRIT,
        "tuesday": Choghadiya.ROG,
        "wednesday": Choghadiya.LABH,
        "thursday": Choghadiya.SHUBH,
        "friday": Choghadiya.CHAR,
        "saturday": Choghadiya.KAAL,
    }
    NIGHT_START = {
        "sunday": Choghadiya.SHUBH,
        "monday": Choghadiya.CHAR,
        "tuesday": Choghadiya.KAAL,
        "wednesday": Choghadiya.UDVEG,
        "thursday": Choghadiya.AMRIT,
        "friday": Choghadiya.ROG,
        "saturday": Choghadiya.LABH,
    }

    @pytest.mark.parametrize("day_name", list(DAY_START))
    def test_day_sequence_starts_and_cycles(self, day_name: str) -> None:
        _, timings = timings_for(day_name)
        parts = sorted(
            of_kind(timings, DayTimingKind.CHOGHADIYA_DAY), key=lambda t: t.starts_utc
        )
        start = self.DAY_START[day_name]
        assert parts[0].choghadiya is start
        offset = CHOGHADIYA_CYCLE.index(start)
        for i, part in enumerate(parts):
            assert part.choghadiya is CHOGHADIYA_CYCLE[(offset + i) % 7]
            assert part.part_index == i + 1

    # The FULL published night sequence, not just its opener. Asserting only
    # the first part is what let a real ordering bug through: the night run
    # walks the ring by -2, and a +1 walk still produces the right first and
    # last entries. Cross-checked against a live Prokerala response for
    # Thursday 2026-01-01 (Amrit·Char·Rog·Kaal·Labh·Udveg·Shubh).
    NIGHT_SEQUENCES = {
        "sunday": ["shubh", "amrit", "char", "rog", "kaal", "labh", "udveg", "shubh"],
        "monday": ["char", "rog", "kaal", "labh", "udveg", "shubh", "amrit", "char"],
        "tuesday": ["kaal", "labh", "udveg", "shubh", "amrit", "char", "rog", "kaal"],
        "wednesday": ["udveg", "shubh", "amrit", "char", "rog", "kaal", "labh", "udveg"],
        "thursday": ["amrit", "char", "rog", "kaal", "labh", "udveg", "shubh", "amrit"],
        "friday": ["rog", "kaal", "labh", "udveg", "shubh", "amrit", "char", "rog"],
        "saturday": ["labh", "udveg", "shubh", "amrit", "char", "rog", "kaal", "labh"],
    }

    @pytest.mark.parametrize("day_name", list(NIGHT_START))
    def test_night_sequence_starts_correctly(self, day_name: str) -> None:
        _, timings = timings_for(day_name)
        parts = sorted(
            of_kind(timings, DayTimingKind.CHOGHADIYA_NIGHT), key=lambda t: t.starts_utc
        )
        assert parts[0].choghadiya is self.NIGHT_START[day_name]

    @pytest.mark.parametrize("day_name", list(NIGHT_SEQUENCES))
    def test_full_night_sequence_matches_published_tables(self, day_name: str) -> None:
        _, timings = timings_for(day_name)
        parts = sorted(
            of_kind(timings, DayTimingKind.CHOGHADIYA_NIGHT), key=lambda t: t.starts_utc
        )
        assert [_name(p) for p in parts] == self.NIGHT_SEQUENCES[day_name]

    DAY_SEQUENCES = {
        "sunday": ["udveg", "char", "labh", "amrit", "kaal", "shubh", "rog", "udveg"],
        "thursday": ["shubh", "rog", "udveg", "char", "labh", "amrit", "kaal", "shubh"],
    }

    @pytest.mark.parametrize("day_name", list(DAY_SEQUENCES))
    def test_full_day_sequence_matches_published_tables(self, day_name: str) -> None:
        _, timings = timings_for(day_name)
        parts = sorted(of_kind(timings, DayTimingKind.CHOGHADIYA_DAY), key=lambda t: t.starts_utc)
        assert [_name(p) for p in parts] == self.DAY_SEQUENCES[day_name]

    def test_the_eighth_part_repeats_the_first(self) -> None:
        """Eight parts over a seven-name cycle — the day closes on its opener."""
        for day_name in WEEK:
            _, timings = timings_for(day_name)
            parts = sorted(
                of_kind(timings, DayTimingKind.CHOGHADIYA_DAY), key=lambda t: t.starts_utc
            )
            assert parts[7].choghadiya is parts[0].choghadiya

    def test_qualities_follow_the_name_not_the_clock(self) -> None:
        _, timings = timings_for("friday")
        expected = {
            Choghadiya.AMRIT: TimingQuality.AUSPICIOUS,
            Choghadiya.SHUBH: TimingQuality.AUSPICIOUS,
            Choghadiya.LABH: TimingQuality.AUSPICIOUS,
            Choghadiya.CHAR: TimingQuality.NEUTRAL,
            Choghadiya.UDVEG: TimingQuality.INAUSPICIOUS,
            Choghadiya.KAAL: TimingQuality.INAUSPICIOUS,
            Choghadiya.ROG: TimingQuality.INAUSPICIOUS,
        }
        for part in of_kind(timings, DayTimingKind.CHOGHADIYA_DAY):
            assert part.choghadiya is not None
            assert part.quality is expected[part.choghadiya]


class TestWeekdayIsLocalNotUtc:
    def test_weekday_comes_from_the_place_not_the_server(self) -> None:
        """A Mumbai Monday starts before UTC Monday does. Reading the weekday
        off a UTC instant would put rahu kaal on the wrong day for half the
        world — the §5.3 wrong-timezone failure in a different coat."""
        pacific = Place(name="Apia", lat=-13.8507, lon=-171.7514, tz="Pacific/Apia")
        d = WEEK["monday"]
        day = sun_day(d, pacific)
        # Local Monday sunrise is still Sunday in UTC at this longitude.
        assert day.sunrise.weekday() == 6
        timings = day_timings(d, pacific)
        part = (day.sunset - day.sunrise) / 8
        rahu = only(timings, DayTimingKind.RAHU_KAAL)
        assert_same_instant(rahu.starts_utc, day.sunrise + part * (2 - 1))  # Monday → part 2
