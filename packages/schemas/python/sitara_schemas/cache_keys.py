"""HAND-WRITTEN MODULE — sanctioned exception to the generated-only rule.

SPEC §7.2 — the astrology cache-key grammar, and the geohash it is built on.

This lives in the shared package because BOTH services depend on the same
strings: sitara-astro builds global fact subjects from geohash4+tradition
(§34.2), and sitara-api builds the Mongo/Redis cache keys. Two copies of this
arithmetic would drift, and a drifting key silently repartitions the cache —
which is how you end up serving one city's timings to another (§5.3, §30.2).

The keys separate user-specific from location-specific from global data
explicitly, and that separation is the contract: a global key can never contain
a user id.

Geohash precision 4 is a ~20 km cell. It is deliberately coarse — a cache key
must never be precise enough to be a location trace (§13).
"""

from datetime import date

from sitara_schemas.facts import MuhuratType, NumerologySystem, Tradition

_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"  # geohash alphabet: no a, i, l, o
DEFAULT_PRECISION = 4


def geohash(lat: float, lon: float, precision: int = DEFAULT_PRECISION) -> str:
    """Standard geohash of a coordinate. Deterministic and stable forever."""
    if not -90.0 <= lat <= 90.0:
        raise ValueError(f"latitude out of range: {lat}")
    if not -180.0 <= lon <= 180.0:
        raise ValueError(f"longitude out of range: {lon}")
    if precision < 1:
        raise ValueError(f"precision must be positive: {precision}")

    lat_range = [-90.0, 90.0]
    lon_range = [-180.0, 180.0]
    out: list[str] = []
    bits = 0
    bit_count = 0
    use_lon = True

    while len(out) < precision:
        span = lon_range if use_lon else lat_range
        value = lon if use_lon else lat
        middle = (span[0] + span[1]) / 2
        # `>=` not `>`: a value exactly on a boundary takes the upper cell,
        # which is what every reference implementation does. (0, 0) must encode
        # as "s000…", not "0000…", or our keys disagree with the world's.
        if value >= middle:
            bits = (bits << 1) | 1
            span[0] = middle
        else:
            bits <<= 1
            span[1] = middle
        use_lon = not use_lon

        bit_count += 1
        if bit_count == 5:
            out.append(_BASE32[bits])
            bits = 0
            bit_count = 0

    return "".join(out)


# --- §7.2 key grammar -------------------------------------------------------
# Verbatim from the spec:
#   natal_chart:{subject}:{engine_v}:{ayanamsa}   permanent until engine bump
#   transits:{date}:{lat_band}:{engine_v}         global,          400-day TTL
#   panchang:{date}:{geohash4}:{tradition}:{provider}  location,    90-day TTL
#   festivals:{year}:{region}:{tradition}         global,   annual refresh
#   muhurat:{type}:{date_range}:{geohash4}        location,        30-day TTL
#   numerology:{subject}:{system}                 permanent until profile edit

LAT_BAND_DEGREES = 10


def lat_band(lat: float) -> str:
    """Coarse latitude band for the global transit cache.

    Transit longitudes are geocentric and do not vary with the observer at all;
    the band exists only so that latitude-sensitive derivations never share a
    row across hemispheres. Ten degrees, signed, floored — "n10" is 10°–20° N.
    """
    if not -90.0 <= lat <= 90.0:
        raise ValueError(f"latitude out of range: {lat}")
    edge = int(abs(lat) // LAT_BAND_DEGREES) * LAT_BAND_DEGREES
    return f"{'s' if lat < 0 else 'n'}{edge}"


def natal_chart_key(subject: str, engine_v: str, ayanamsa: str) -> str:
    """USER-SPECIFIC. Permanent until an engine bump (§7.2)."""
    return f"natal_chart:{subject}:{engine_v}:{ayanamsa}"


def transits_key(on: date, lat: float, engine_v: str) -> str:
    """GLOBAL. Shared by every user at that latitude band (§7.2, 400-day TTL)."""
    return f"transits:{on.isoformat()}:{lat_band(lat)}:{engine_v}"


def panchang_key(on: date, lat: float, lon: float, tradition: Tradition, provider: str) -> str:
    """LOCATION-SPECIFIC, shared across users (§7.2, 90-day TTL).

    No user id, by construction: the only inputs are a date, a place and a
    tradition. This is what lets thousands of users share one document (§7.1).
    """
    return f"panchang:{on.isoformat()}:{geohash(lat, lon)}:{tradition.value}:{provider}"


def festivals_key(year: int, region: str, tradition: Tradition) -> str:
    """GLOBAL. Annual refresh + admin override (§7.2)."""
    return f"festivals:{year}:{region}:{tradition.value}"


def muhurat_key(
    muhurat_type: MuhuratType, date_from: date, date_to: date, lat: float, lon: float
) -> str:
    """LOCATION-SPECIFIC (§7.2, 30-day TTL). The date_range is the window the
    finder searched, so a re-query over a different range is a different key."""
    span = f"{date_from.isoformat()}_{date_to.isoformat()}"
    return f"muhurat:{muhurat_type.value}:{span}:{geohash(lat, lon)}"


def numerology_key(subject: str, system: NumerologySystem) -> str:
    """USER-SPECIFIC. Permanent until the profile is edited (§7.2)."""
    return f"numerology:{subject}:{system.value}"


GLOBAL_KEY_PREFIXES = ("transits:", "panchang:", "festivals:", "muhurat:")
USER_KEY_PREFIXES = ("natal_chart:", "numerology:")


def is_global_key(key: str) -> bool:
    """True for keys that are shared across users and must never embed an id."""
    return key.startswith(GLOBAL_KEY_PREFIXES)
