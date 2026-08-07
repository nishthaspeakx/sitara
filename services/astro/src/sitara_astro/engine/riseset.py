"""Solar day boundaries for a local date at a place (SPEC §5.2 Layer A).

Every panchang day division hangs off sunrise, so this module answers one
question precisely: for the LOCAL date the user means, when does the Sun rise,
cross the meridian, set, and rise again?

The local date is the anchor, never a UTC date — a cache keyed by local date
and filled from a UTC instant is the §5.3 "cached data for the wrong timezone"
failure. Polar day/night produce no fact at all (§5.3: never invent a value).
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sitara_schemas import ErrorCode

from sitara_astro.engine.ephemeris import sun_event_after
from sitara_astro.engine.inputs import Place
from sitara_astro.errors import AstroError

# A search that starts one day early always brackets the target date's sunrise,
# even at longitudes where local midnight sits far from UTC midnight.
_LOOKBACK = timedelta(days=1)


class NoRiseOrSet(AstroError):
    """The Sun does not rise or does not set on this local date at this place.

    Polar summer and polar winter are correct answers, not errors in the
    engine — but they mean no day-timing fact exists, so callers must degrade
    honestly rather than serve a fabricated window.
    """

    def __init__(self, place_tz: str, local_date: date) -> None:
        super().__init__(
            ErrorCode.ASTRO_INSUFFICIENT_BIRTH_DATA,
            message_key="errors.astro.no_sunrise_at_location",
            # §13: a tz name and a date are not PII.
            detail=f"no rise/set on {local_date.isoformat()} in {place_tz}",
        )


@dataclass(frozen=True)
class SolarDay:
    """The four instants every day division is measured from. All UTC."""

    local_date: date
    sunrise: datetime
    solar_noon: datetime
    sunset: datetime
    next_sunrise: datetime

    @property
    def day_length(self) -> timedelta:
        return self.sunset - self.sunrise

    @property
    def night_length(self) -> timedelta:
        return self.next_sunrise - self.sunset


def _zone(place: Place) -> ZoneInfo:
    try:
        return ZoneInfo(place.tz)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise AstroError(ErrorCode.ASTRO_PLACE_UNRESOLVED) from exc


def sun_day(local_date: date, place: Place) -> SolarDay:
    """Rise/noon/set/next-rise for `local_date` as lived at `place`.

    Walks forward from a point safely before the local day begins until it
    finds the first sunrise that lands on the requested local date, so a place
    whose UTC offset pushes sunrise across the UTC date line is still answered
    for the day the user actually means.
    """
    zone = _zone(place)
    search_from = datetime.combine(local_date, time(0, 0), tzinfo=zone).astimezone(UTC) - _LOOKBACK

    sunrise = _first_rise_on(local_date, place, zone, search_from)
    sunset = sun_event_after(sunrise, place.lat, place.lon, "set")
    solar_noon = sun_event_after(sunrise, place.lat, place.lon, "noon")
    next_sunrise = sun_event_after(sunrise, place.lat, place.lon, "rise")

    if sunset is None or solar_noon is None or next_sunrise is None:
        raise NoRiseOrSet(place.tz, local_date)
    # Guards the ordering the fact model requires; a place inside the polar
    # circle can return events that belong to a different solar day.
    if not sunrise < solar_noon < sunset < next_sunrise:
        raise NoRiseOrSet(place.tz, local_date)

    return SolarDay(
        local_date=local_date,
        sunrise=sunrise,
        solar_noon=solar_noon,
        sunset=sunset,
        next_sunrise=next_sunrise,
    )


def _first_rise_on(
    local_date: date, place: Place, zone: ZoneInfo, search_from: datetime
) -> datetime:
    """The sunrise whose LOCAL date is `local_date`."""
    cursor = search_from
    for _ in range(4):  # at most two candidate sunrises fall in the window
        candidate = sun_event_after(cursor, place.lat, place.lon, "rise")
        if candidate is None:
            raise NoRiseOrSet(place.tz, local_date)
        candidate_local = candidate.astimezone(zone).date()
        if candidate_local == local_date:
            return candidate
        if candidate_local > local_date:
            break
        cursor = candidate
    raise NoRiseOrSet(place.tz, local_date)
