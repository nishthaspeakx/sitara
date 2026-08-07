"""Sunrise/sunset/solar-noon — SPEC §5.2 Layer A.

This is the rung §8's degradation ladder calls "internal panchang (if within
validated scope)": when DivineAPI is down, day timings still compute from our
own ephemeris rather than vanishing.

These are PROPERTY tests — orderings, symmetries and physical invariants that
hold at any place and date. Exact published-value parity is the golden set's
job (§5.2 Layer C, release-blocking at <99.9%), not this file's.
"""

from datetime import UTC, date, timedelta
from zoneinfo import ZoneInfo

import pytest
from sitara_schemas import ErrorCode

from sitara_astro.engine.inputs import Place
from sitara_astro.engine.riseset import NoRiseOrSet, sun_day
from sitara_astro.errors import AstroError

MUMBAI = Place(name="Mumbai", lat=19.0760, lon=72.8777, tz="Asia/Kolkata")
LONDON = Place(name="London", lat=51.5074, lon=-0.1278, tz="Europe/London")
GREENWICH = Place(name="Greenwich", lat=51.4779, lon=0.0, tz="Etc/UTC")
TROMSO = Place(name="Tromso", lat=69.6496, lon=18.9560, tz="Europe/Oslo")
QUITO = Place(name="Quito", lat=-0.1807, lon=-78.4678, tz="America/Guayaquil")


class TestOrdering:
    def test_events_are_ordered_and_utc(self) -> None:
        day = sun_day(date(2026, 8, 7), MUMBAI)
        assert day.sunrise < day.solar_noon < day.sunset < day.next_sunrise
        for moment in (day.sunrise, day.solar_noon, day.sunset, day.next_sunrise):
            assert moment.tzinfo is UTC

    def test_sunrise_falls_on_the_requested_local_date(self) -> None:
        """A cache keyed by local date must not be filled with the wrong day's
        sunrise — that is exactly the §5.3 'cached data for the wrong timezone'
        failure."""
        for place in (MUMBAI, LONDON, QUITO):
            local_date = date(2026, 8, 7)
            day = sun_day(local_date, place)
            assert day.sunrise.astimezone(ZoneInfo(place.tz)).date() == local_date

    def test_next_sunrise_is_the_following_local_date(self) -> None:
        day = sun_day(date(2026, 8, 7), MUMBAI)
        local = day.next_sunrise.astimezone(ZoneInfo(MUMBAI.tz))
        assert local.date() == date(2026, 8, 8)

    def test_solar_noon_bisects_the_day(self) -> None:
        """Refraction makes this approximate, not exact — a few minutes, never
        an hour. A gross failure here means lon/lat were swapped."""
        day = sun_day(date(2026, 8, 7), MUMBAI)
        midpoint = day.sunrise + (day.sunset - day.sunrise) / 2
        assert abs((day.solar_noon - midpoint).total_seconds()) < 5 * 60


class TestPhysics:
    def test_equinox_day_is_about_twelve_hours_everywhere(self) -> None:
        equinox = date(2026, 3, 20)
        for place in (MUMBAI, LONDON, QUITO):
            length = sun_day(equinox, place).day_length
            assert timedelta(hours=11, minutes=50) < length < timedelta(hours=12, minutes=20)

    def test_summer_days_are_longer_further_north(self) -> None:
        june = date(2026, 6, 21)
        assert sun_day(june, LONDON).day_length > sun_day(june, MUMBAI).day_length
        assert sun_day(june, MUMBAI).day_length > sun_day(june, QUITO).day_length

    def test_southern_hemisphere_seasons_invert(self) -> None:
        """§5.2 Layer C names southern-hemisphere cases explicitly."""
        sydney = Place(name="Sydney", lat=-33.8688, lon=151.2093, tz="Australia/Sydney")
        june = sun_day(date(2026, 6, 21), sydney).day_length
        december = sun_day(date(2026, 12, 21), sydney).day_length
        assert december > june

    def test_greenwich_solar_noon_sits_near_twelve_ut(self) -> None:
        """Only the equation of time (±17 min) may separate them."""
        for day_of_year in (date(2026, 2, 11), date(2026, 5, 14), date(2026, 11, 3)):
            noon = sun_day(day_of_year, GREENWICH).solar_noon
            offset_minutes = (noon.hour - 12) * 60 + noon.minute
            assert abs(offset_minutes) <= 17


class TestPublishedAnchor:
    def test_mumbai_sunrise_matches_the_almanac(self) -> None:
        """One anchored value so a wholesale regression cannot hide behind
        properties. Published Mumbai sunrise 2026-08-07 is 06:17 IST under the
        upper-limb-with-refraction definition we use."""
        day = sun_day(date(2026, 8, 7), MUMBAI)
        local = day.sunrise.astimezone(ZoneInfo("Asia/Kolkata"))
        assert (local.hour, local.minute) == (6, 17)


class TestDstAndPolar:
    def test_dst_transition_shifts_local_sunrise_by_an_hour(self) -> None:
        """London 2026-03-29 is a spring-forward date; UTC sunrise creeps a few
        minutes earlier while LOCAL sunrise jumps roughly an hour later."""
        before = sun_day(date(2026, 3, 28), LONDON)
        after = sun_day(date(2026, 3, 29), LONDON)
        zone = ZoneInfo("Europe/London")
        before_local = before.sunrise.astimezone(zone)
        after_local = after.sunrise.astimezone(zone)
        jump = (after_local.hour * 60 + after_local.minute) - (
            before_local.hour * 60 + before_local.minute
        )
        assert 55 <= jump <= 65

    def test_polar_midnight_sun_declines_honestly(self) -> None:
        """§5.3: never invent a value. No sunset means no fact, not a guess."""
        with pytest.raises(NoRiseOrSet):
            sun_day(date(2026, 6, 21), TROMSO)

    def test_polar_failure_surfaces_as_the_canonical_envelope(self) -> None:
        """NoRiseOrSet is an AstroError, so the §34.4 envelope renders itself."""
        with pytest.raises(AstroError) as exc:
            sun_day(date(2026, 12, 21), TROMSO)
        assert exc.value.code is ErrorCode.ASTRO_INSUFFICIENT_BIRTH_DATA


class TestDeterminism:
    def test_repeated_calls_agree_exactly(self) -> None:
        """Facts are cached globally and shared across thousands of users
        (§7.1) — a wobbling sunrise would poison every brief that day."""
        first = sun_day(date(2026, 8, 7), MUMBAI)
        second = sun_day(date(2026, 8, 7), MUMBAI)
        assert first == second
