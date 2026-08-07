"""Place resolution — SPEC §30.2.

Every timing endpoint takes an EXPLICIT place: "wedding in Jaipur" must be
computed for Jaipur, in Jaipur's timezone, and labelled with Jaipur. So a
resolver has one job — turn what the caller said into a coordinate, an IANA
zone, and the label we will show back.

Two inputs are accepted: a city name from the seed gazetteer, or a fully
specified place (lat/lon/tz/label). Anything else is declined with
ASTRO_PLACE_UNRESOLVED — we never fall back to a default city, because a
silently-wrong city produces confidently-wrong timings (§5.3).

The §5.2 Google Geocoding + Time Zone resolver slots in behind this same
interface later; no endpoint changes when it does.
"""

import json
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sitara_schemas import ErrorCode

from sitara_api.errors import ApiError
from sitara_api.panchang.providers.base import ResolvedPlace

GAZETTEER_PATH = Path(__file__).with_name("gazetteer.json")


@dataclass(frozen=True)
class City:
    id: str
    label: str
    lat: float
    lon: float
    tz: str
    region: str

    def to_place(self) -> ResolvedPlace:
        return ResolvedPlace(label=self.label, lat=self.lat, lon=self.lon, tz=self.tz)


def _normalise(name: str) -> str:
    """Fold case, accents and spacing so "Bengaluru", "bangalore" and
    "  BENGALURU " are one lookup."""
    decomposed = unicodedata.normalize("NFKD", name.strip().casefold())
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.replace("-", " ").split())


class PlaceResolver(Protocol):
    def resolve_city(self, name: str) -> ResolvedPlace: ...

    def region_for(self, place: ResolvedPlace) -> str: ...


class GazetteerResolver:
    """Seed resolver over the committed city list.

    Canonical coordinates matter beyond convenience: because every user in a
    city resolves to the SAME point, they all land on one §7.2 cache key — that
    is the mechanism behind §7.1's "thousands of users share one panchang doc",
    not the luck of which side of a geohash cell edge someone is standing on.
    """

    def __init__(self, path: Path = GAZETTEER_PATH) -> None:
        raw = json.loads(path.read_text(encoding="utf-8"))
        self._cities: dict[str, City] = {}
        self._by_id: dict[str, City] = {}
        for entry in raw["cities"]:
            city = City(
                id=entry["id"],
                label=entry["label"],
                lat=entry["lat"],
                lon=entry["lon"],
                tz=entry["tz"],
                region=entry["region"],
            )
            self._by_id[city.id] = city
            for name in (city.id, city.label, *entry.get("aliases", [])):
                self._cities[_normalise(name)] = city

    @property
    def cities(self) -> tuple[City, ...]:
        return tuple(self._by_id.values())

    def resolve_city(self, name: str) -> ResolvedPlace:
        city = self._cities.get(_normalise(name))
        if city is None:
            # No default, ever: a wrong city is worse than no answer (§5.3).
            raise ApiError(ErrorCode.ASTRO_PLACE_UNRESOLVED)
        return city.to_place()

    def region_for(self, place: ResolvedPlace) -> str:
        city = self._cities.get(_normalise(place.label))
        return city.region if city else "in-north"


def resolve_explicit(label: str, lat: float, lon: float, tz: str) -> ResolvedPlace:
    """Accept a caller-supplied place, validating the zone against the IANA
    tzdb. An astrology vendor is never trusted for timezone handling (§5.2)."""
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ApiError(ErrorCode.ASTRO_PLACE_UNRESOLVED) from exc
    if not label.strip():
        raise ApiError(ErrorCode.ASTRO_PLACE_UNRESOLVED)
    try:
        return ResolvedPlace(label=label.strip(), lat=lat, lon=lon, tz=tz)
    except ValueError as exc:  # out-of-range coordinates
        raise ApiError(ErrorCode.ASTRO_PLACE_UNRESOLVED) from exc


@lru_cache(maxsize=1)
def default_resolver() -> GazetteerResolver:
    return GazetteerResolver()
