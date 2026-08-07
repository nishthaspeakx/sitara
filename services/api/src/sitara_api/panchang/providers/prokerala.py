"""Prokerala adapter — SPEC §5.2 Layer B CROSS-CHECK ORACLE.

"Prokerala Ruby tier runs in parallel as the independent cross-check oracle
(its 24h-cache ToS is honoured: cross-check calls are ephemeral)."

Two constraints shape this adapter:

* **Never the system of record.** §5.2's provider table is explicit: "ToS: cache
  must refresh ≤24h, purge on termination — cannot be system of record". We
  honour it the strict way — PanchangCache REFUSES to persist anything from
  this provider, so the rule cannot be forgotten at a call site.
* **Never the winner.** §32.2: on disagreement the fact still serves from
  DivineAPI. Prokerala raises its hand; it does not overrule.

⚠️ SHAPE STATUS: as with DivineAPI, the paths and field names are the adapter's
assumption until `python -m sitara_api.panchang.record` confirms them against a
live trial account.
"""

import datetime as dt
import time

from sitara_schemas.facts import DayTimingKind, TimingQuality

from sitara_api.panchang.providers.base import (
    BoundaryReading,
    MuhuratQuery,
    MuhuratWindow,
    NormalisedDayTimings,
    NormalisedMuhurat,
    NormalisedPanchang,
    PanchangQuery,
    ProviderName,
    TimingWindow,
)
from sitara_api.panchang.providers.http import (
    ProviderMisconfigured,
    ProviderUnavailable,
    VendorClient,
    unparseable,
)
from sitara_api.panchang.providers.parsing import ShapeError, pick, require, to_index, to_utc

DEFAULT_PATHS = {
    "token": "/token",
    "panchang": "/v2/astrology/panchang",
    "day_timings": "/v2/astrology/choghadiya",
    "muhurat": "/v2/astrology/auspicious-period",
}

AYANAMSA_LAHIRI = 1  # §5.2: Lahiri is our default; the cross-check must match

_BAND_KINDS = {
    "rahu": DayTimingKind.RAHU_KAAL,
    "yamaganda": DayTimingKind.YAMAGANDA,
    "gulika": DayTimingKind.GULIKAI,
}


class ProkeralaProvider:
    """Independent second opinion. Ephemeral by ToS — never cached."""

    name = ProviderName.PROKERALA

    def __init__(
        self,
        client: VendorClient,
        client_id: str | None,
        client_secret: str | None,
        paths: dict[str, str] | None = None,
        clock=time.monotonic,  # noqa: ANN001
    ) -> None:
        self._client = client
        self._client_id = client_id
        self._client_secret = client_secret
        self._paths = {**DEFAULT_PATHS, **(paths or {})}
        self._clock = clock
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    async def _access_token(self) -> str:
        """OAuth2 client-credentials, cached until shortly before expiry.

        Re-authenticating per call would burn the Ruby tier's request budget on
        tokens rather than facts.
        """
        if not self._client_id or not self._client_secret:
            raise ProviderMisconfigured(
                self.name, "PROKERALA_CLIENT_ID/CLIENT_SECRET not configured"
            )
        if self._token is not None and self._clock() < self._token_expires_at:
            return self._token

        payload = await self._client.request(
            "POST",
            self._paths["token"],
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
        )
        token = pick(payload, "access_token")
        if not isinstance(token, str) or not token:
            raise ProviderUnavailable(self.name, "no access_token in token response")
        expires_in = pick(payload, "expires_in")
        lifetime = float(expires_in) if isinstance(expires_in, (int, float)) else 3600.0
        self._token = token
        # 60-second safety margin against clock skew mid-flight.
        self._token_expires_at = self._clock() + max(lifetime - 60.0, 30.0)
        return token

    async def _get(self, path_key: str, params: dict) -> dict:
        token = await self._access_token()
        return await self._client.request(
            "GET",
            self._paths[path_key],
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )

    def _base_params(self, place, on: dt.date) -> dict:  # noqa: ANN001
        # Sunrise-anchored day: ask about the local morning, not midnight UTC.
        local_morning = dt.datetime.combine(on, dt.time(6, 0))
        return {
            "ayanamsa": AYANAMSA_LAHIRI,
            "coordinates": f"{place.lat},{place.lon}",
            "datetime": local_morning.isoformat(),
            "la": "en",  # facts only; user-facing copy is ours (§2.4)
        }

    async def panchang(self, query: PanchangQuery) -> NormalisedPanchang:
        raw = await self._get("panchang", self._base_params(query.place, query.local_date))
        tz = query.place.tz
        try:
            tithi = require(raw, "data.tithi.0", "data.tithi")
            nakshatra = require(raw, "data.nakshatra.0", "data.nakshatra")
            return NormalisedPanchang(
                provider=self.name,
                local_date=query.local_date,
                sunrise_utc=to_utc(require(raw, "data.sunrise", "sunrise"), tz),
                sunset_utc=to_utc(require(raw, "data.sunset", "sunset"), tz),
                tithi=BoundaryReading(
                    index=to_index(require(tithi, "index", "number", "id")),
                    starts_utc=to_utc(require(tithi, "start", "starts_at"), tz),
                    ends_utc=to_utc(require(tithi, "end", "ends_at"), tz),
                ),
                nakshatra=BoundaryReading(
                    index=to_index(require(nakshatra, "index", "number", "id")),
                    starts_utc=to_utc(require(nakshatra, "start", "starts_at"), tz),
                    ends_utc=to_utc(require(nakshatra, "end", "ends_at"), tz),
                ),
            )
        except (ShapeError, ValueError) as exc:
            raise unparseable(self.name, str(exc)) from exc

    async def day_timings(self, query: PanchangQuery) -> NormalisedDayTimings:
        raw = await self._get("day_timings", self._base_params(query.place, query.local_date))
        tz = query.place.tz
        windows: list[TimingWindow] = []
        try:
            for field, kind in _BAND_KINDS.items():
                band = pick(raw, f"data.{field}", f"data.{field}_kaal", field)
                if band is None:
                    continue
                windows.append(
                    TimingWindow(
                        timing=kind,
                        starts_utc=to_utc(require(band, "start", "starts_at"), tz),
                        ends_utc=to_utc(require(band, "end", "ends_at"), tz),
                        quality=TimingQuality.INAUSPICIOUS,
                    )
                )
        except (ShapeError, ValueError) as exc:
            raise unparseable(self.name, str(exc)) from exc

        if not windows:
            raise unparseable(self.name, "no recognisable day timings")
        return NormalisedDayTimings(
            provider=self.name, local_date=query.local_date, windows=tuple(windows)
        )

    async def muhurat(self, query: MuhuratQuery) -> NormalisedMuhurat:
        params = self._base_params(query.place, query.date_from)
        params["type"] = query.muhurat_type.value
        raw = await self._get("muhurat", params)
        tz = query.place.tz
        try:
            entries = require(raw, "data.muhurat", "data.auspicious_period", "data.periods")
            windows = tuple(
                MuhuratWindow(
                    starts_utc=to_utc(require(entry, "start", "starts_at"), tz),
                    ends_utc=to_utc(require(entry, "end", "ends_at"), tz),
                    quality=TimingQuality.AUSPICIOUS,
                )
                for entry in entries
            )
        except (ShapeError, ValueError) as exc:
            raise unparseable(self.name, str(exc)) from exc
        return NormalisedMuhurat(
            provider=self.name, muhurat_type=query.muhurat_type, windows=windows
        )
