"""SPEC §7.2 — the astrology cache-key grammar and its geohash.

The key format is a frozen contract shared by sitara-astro and sitara-api;
these tests pin it against published reference values and against the spec's
literal key strings, so a refactor cannot silently repartition the cache.
"""

from datetime import date

import pytest

from sitara_schemas.cache_keys import (
    festivals_key,
    geohash,
    is_global_key,
    lat_band,
    muhurat_key,
    natal_chart_key,
    numerology_key,
    panchang_key,
    transits_key,
)
from sitara_schemas.facts import MuhuratType, NumerologySystem, Tradition


class TestReferenceValues:
    @pytest.mark.parametrize(
        ("lat", "lon", "expected"),
        [
            (57.64911, 10.40744, "u4pruydqqvj"),  # the canonical Wikipedia example
            (0.0, 0.0, "s0000000000"),
            (-90.0, -180.0, "00000000000"),
            (90.0, 180.0, "zzzzzzzzzzz"),
        ],
    )
    def test_matches_published_geohashes(self, lat: float, lon: float, expected: str) -> None:
        assert geohash(lat, lon, len(expected)) == expected

    def test_prefixes_are_stable_across_precisions(self) -> None:
        """A precision-4 key must be the precision-11 key's prefix, or cache
        entries at different precisions would disagree about the same place."""
        full = geohash(19.0760, 72.8777, 11)
        for p in range(1, 12):
            assert geohash(19.0760, 72.8777, p) == full[:p]


class TestCacheKeyProperties:
    def test_default_precision_is_four(self) -> None:
        """§7.2 fixes geohash4 — a change here silently reshards every cache."""
        assert len(geohash(19.0760, 72.8777)) == 4

    def test_a_cell_is_roughly_city_scale(self) -> None:
        """A precision-4 cell is ~20 km, so points a few km apart usually — but
        NOT always — collapse together. Bandra and Colaba are 15 km apart and
        genuinely land either side of a cell edge.

        Sharing (§7.1: 'thousands of users share one panchang doc') therefore
        does NOT come from grid luck. It comes from keying the cache off the
        RESOLVED CITY's canonical coordinate, so every Mumbai user hits one key
        no matter where in Mumbai they stand. That is asserted where the
        resolver lives, not here."""
        assert geohash(19.0596, 72.8295) == geohash(19.0760, 72.8777)  # Bandra ≈ city centre
        assert geohash(19.0596, 72.8295) != geohash(18.9220, 72.8347)  # Colaba, other side

    def test_distant_cities_never_share_a_cell(self) -> None:
        """§30.2 acceptance: no cached timing may cross cities."""
        cities = {
            "mumbai": (19.0760, 72.8777),
            "delhi": (28.6139, 77.2090),
            "chennai": (13.0827, 80.2707),
            "kolkata": (22.5726, 88.3639),
            "london": (51.5074, -0.1278),
        }
        keys = {name: geohash(*coords) for name, coords in cities.items()}
        assert len(set(keys.values())) == len(cities), keys

    def test_is_deterministic(self) -> None:
        assert geohash(19.0760, 72.8777) == geohash(19.0760, 72.8777)

    def test_output_is_url_and_key_safe(self) -> None:
        """The key is interpolated into a fact-ID subject, whose grammar allows
        only [A-Za-z0-9_-] (§34.2)."""
        code = geohash(19.0760, 72.8777, 8)
        assert code.isalnum() and code.islower()
        for banned in "ailo":
            assert banned not in code


class TestValidation:
    @pytest.mark.parametrize(("lat", "lon"), [(91.0, 0.0), (-91.0, 0.0), (0.0, 181.0)])
    def test_out_of_range_rejected(self, lat: float, lon: float) -> None:
        with pytest.raises(ValueError):
            geohash(lat, lon)

    def test_zero_precision_rejected(self) -> None:
        with pytest.raises(ValueError):
            geohash(19.0, 72.0, 0)


class TestSpecKeyGrammar:
    """The literal §7.2 strings. If one of these changes, every cached row in
    production is orphaned — so they are pinned character for character."""

    def test_panchang_key(self) -> None:
        assert (
            panchang_key(date(2026, 8, 8), 19.0760, 72.8777, Tradition.AMANTA, "divineapi")
            == "panchang:2026-08-08:te7u:amanta:divineapi"
        )

    def test_transits_key(self) -> None:
        assert transits_key(date(2026, 8, 8), 19.076, "v0.1.0") == "transits:2026-08-08:n10:v0.1.0"

    def test_festivals_key(self) -> None:
        assert festivals_key(2026, "in-north", Tradition.PURNIMANTA) == (
            "festivals:2026:in-north:purnimanta"
        )

    def test_muhurat_key(self) -> None:
        assert muhurat_key(
            MuhuratType.MARRIAGE, date(2026, 11, 1), date(2026, 11, 30), 26.9124, 75.7873
        ) == "muhurat:marriage:2026-11-01_2026-11-30:tsvc"

    def test_natal_and_numerology_keys(self) -> None:
        assert natal_chart_key("user123", "v0.1.0", "lahiri") == (
            "natal_chart:user123:v0.1.0:lahiri"
        )
        assert numerology_key("user123", NumerologySystem.CHALDEAN) == (
            "numerology:user123:chaldean"
        )


class TestUserVsGlobalSeparation:
    """§7.2 makes the separation explicit; §34.2 depends on it. A user id in a
    shared key would leak one person's data into thousands of briefs."""

    def test_global_keys_are_classified_as_global(self) -> None:
        for key in (
            panchang_key(date(2026, 8, 8), 19.076, 72.877, Tradition.AMANTA, "divineapi"),
            transits_key(date(2026, 8, 8), 19.076, "v0.1.0"),
            festivals_key(2026, "in-north", Tradition.AMANTA),
            muhurat_key(MuhuratType.GENERAL, date(2026, 11, 1), date(2026, 11, 2), 26.9, 75.7),
        ):
            assert is_global_key(key)

    def test_user_keys_are_not_global(self) -> None:
        assert not is_global_key(natal_chart_key("user123", "v0.1.0", "lahiri"))
        assert not is_global_key(numerology_key("user123", NumerologySystem.CHALDEAN))

    def test_no_global_key_builder_accepts_a_subject(self) -> None:
        """Structural guarantee, not a convention: the global builders take a
        date, a place and a tradition — there is no parameter a caller could
        pass an identity through."""
        import inspect

        for builder in (panchang_key, transits_key, festivals_key, muhurat_key):
            params = set(inspect.signature(builder).parameters)
            assert not params & {"subject", "user_id", "user"}, builder.__name__


class TestLatBand:
    @pytest.mark.parametrize(
        ("lat", "expected"),
        [(0.0, "n0"), (9.9, "n0"), (10.0, "n10"), (19.076, "n10"), (-0.1, "s0"), (-33.87, "s30")],
    )
    def test_bands(self, lat: float, expected: str) -> None:
        assert lat_band(lat) == expected

    def test_hemispheres_never_share_a_band(self) -> None:
        assert lat_band(5.0) != lat_band(-5.0)

    def test_out_of_range_rejected(self) -> None:
        with pytest.raises(ValueError):
            lat_band(95.0)
