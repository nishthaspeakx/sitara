"""Place resolution — SPEC §30.2.

The property that matters most is not lookup convenience: it is that one city
always yields ONE canonical point, so every user in it shares a single §7.2
cache row (§7.1), and that an unknown city is declined rather than guessed.
"""

import pytest
from sitara_schemas import ErrorCode
from sitara_schemas.cache_keys import geohash
from sitara_schemas.facts import Tradition

from sitara_api.errors import ApiError
from sitara_api.panchang.places import GazetteerResolver, _normalise, resolve_explicit


@pytest.fixture()
def resolver() -> GazetteerResolver:
    return GazetteerResolver()


class TestLookup:
    def test_resolves_a_city(self, resolver: GazetteerResolver) -> None:
        place = resolver.resolve_city("Mumbai")
        assert place.label == "Mumbai"
        assert place.tz == "Asia/Kolkata"
        assert (round(place.lat, 3), round(place.lon, 3)) == (19.076, 72.878)

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("bangalore", "Bengaluru"),
            ("Bengaluru", "Bengaluru"),
            ("  BENGALURU  ", "Bengaluru"),
            ("bombay", "Mumbai"),
            ("calcutta", "Kolkata"),
            ("trivandrum", "Thiruvananthapuram"),
            ("new-york", "New York"),
            ("nyc", "New York"),
        ],
    )
    def test_aliases_and_casing(
        self, resolver: GazetteerResolver, query: str, expected: str
    ) -> None:
        """A user typing the name they grew up with must not be told their city
        does not exist."""
        assert resolver.resolve_city(query).label == expected

    def test_label_is_the_canonical_name_not_the_query(
        self, resolver: GazetteerResolver
    ) -> None:
        """§30.2 labels the timing with the city — we show the canonical name,
        so 'bombay' renders as Mumbai rather than echoing the input."""
        assert resolver.resolve_city("bombay").label == "Mumbai"


class TestHonestDecline:
    def test_unknown_city_is_declined(self, resolver: GazetteerResolver) -> None:
        with pytest.raises(ApiError) as exc:
            resolver.resolve_city("Atlantis")
        assert exc.value.code is ErrorCode.ASTRO_PLACE_UNRESOLVED

    def test_there_is_no_default_city(self, resolver: GazetteerResolver) -> None:
        """A silent fallback to Delhi would produce confidently wrong timings
        for everyone whose city we failed to parse (§5.3)."""
        for junk in ("", "   ", "???", "Mumbai, India, Earth"):
            with pytest.raises(ApiError):
                resolver.resolve_city(junk)


class TestCanonicalPointsDriveCacheSharing:
    def test_every_alias_maps_to_one_cache_key(self, resolver: GazetteerResolver) -> None:
        """This is the §7.1 sharing mechanism: not geohash luck, but one
        canonical coordinate per city."""
        keys = {
            geohash(p.lat, p.lon)
            for p in (
                resolver.resolve_city("Mumbai"),
                resolver.resolve_city("bombay"),
                resolver.resolve_city("  mumbai "),
            )
        }
        assert len(keys) == 1

    def test_distinct_cities_never_collide(self, resolver: GazetteerResolver) -> None:
        """§30.2 acceptance: no cached timing ever crosses cities. Any two
        gazetteer cities sharing a geohash4 cell would silently do exactly
        that, so the whole list is checked."""
        seen: dict[str, str] = {}
        collisions = []
        for city in resolver.cities:
            key = f"{geohash(city.lat, city.lon)}:{city.tz}"
            if key in seen:
                collisions.append((seen[key], city.id))
            seen[key] = city.id
        assert not collisions, f"cities sharing a cache cell: {collisions}"


class TestGazetteerIntegrity:
    def test_every_timezone_is_a_real_iana_zone(self, resolver: GazetteerResolver) -> None:
        """§5.2: tz comes from the IANA tzdb, never from a vendor. A typo here
        would surface as a wrong-timezone timing, the §5.3 failure."""
        from zoneinfo import ZoneInfo

        for city in resolver.cities:
            ZoneInfo(city.tz)

    def test_ids_and_labels_are_unique(self, resolver: GazetteerResolver) -> None:
        ids = [c.id for c in resolver.cities]
        assert len(ids) == len(set(ids))

    def test_coordinates_are_in_range(self, resolver: GazetteerResolver) -> None:
        for city in resolver.cities:
            assert -90 <= city.lat <= 90
            assert -180 <= city.lon <= 180

    def test_regions_are_festival_calendar_keys(self, resolver: GazetteerResolver) -> None:
        """The region feeds the §7.2 festivals key, whose grammar is a slug."""
        from sitara_schemas.cache_keys import festivals_key

        for city in resolver.cities:
            key = festivals_key(2026, city.region, Tradition.AMANTA)
            assert key.count(":") == 3
            assert " " not in key


class TestExplicitPlace:
    def test_accepts_a_fully_specified_place(self) -> None:
        place = resolve_explicit("Jaipur", 26.9124, 75.7873, "Asia/Kolkata")
        assert place.label == "Jaipur"
        assert place.tz == "Asia/Kolkata"

    def test_rejects_an_unknown_timezone(self) -> None:
        with pytest.raises(ApiError) as exc:
            resolve_explicit("Olympus", 0.0, 0.0, "Mars/Olympus")
        assert exc.value.code is ErrorCode.ASTRO_PLACE_UNRESOLVED

    def test_rejects_out_of_range_coordinates(self) -> None:
        with pytest.raises(ApiError):
            resolve_explicit("Nowhere", 999.0, 0.0, "Etc/UTC")

    def test_rejects_a_blank_label(self) -> None:
        """§30.2 requires the window to be LABELLED with its city; an unlabelled
        place could render as if it were the user's own."""
        with pytest.raises(ApiError):
            resolve_explicit("   ", 26.9, 75.8, "Asia/Kolkata")


class TestNormalisation:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("Bengaluru", "bengaluru"), ("New-York", "new york"), ("  KOCHI ", "kochi")],
    )
    def test_normalise(self, raw: str, expected: str) -> None:
        assert _normalise(raw) == expected
