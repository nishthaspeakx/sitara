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

SHAPE STATUS: **VERIFIED** against the live sandbox API on 2026-01-01 (Mumbai).
Paths, field names and three vendor-specific quirks are recorded in the methods
below: krishna-first tithi numbering, 0-based nakshatra ids, and the absence of
any typed muhurat finder. The recorded payloads are in
tests/panchang/fixtures/prokerala/.

Sandbox note: the trial account rejects every date but January 1st (error 1004),
which is why the fixtures sit on that date. It pins the SHAPE, which is what
they exist for.
"""

import datetime as dt
import time
from zoneinfo import ZoneInfo

from sitara_schemas.facts import Choghadiya, DayTimingKind, MuhuratType, TimingQuality

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

# Their spellings → our closed enum. "Amrut" is the one that differs.
_CHOGHADIYA_NAMES = {
    "udveg": Choghadiya.UDVEG,
    "udvega": Choghadiya.UDVEG,
    "char": Choghadiya.CHAR,
    "chara": Choghadiya.CHAR,
    "labh": Choghadiya.LABH,
    "amrut": Choghadiya.AMRIT,
    "amrit": Choghadiya.AMRIT,
    "kaal": Choghadiya.KAAL,
    "kal": Choghadiya.KAAL,
    "shubh": Choghadiya.SHUBH,
    "subh": Choghadiya.SHUBH,
    "rog": Choghadiya.ROG,
}

# Quality is derived from the NAME on our side, identically for every provider,
# so the two vendors stay comparable (§5.2 Layer D).
_CHOGHADIYA_QUALITY = {
    Choghadiya.AMRIT: TimingQuality.AUSPICIOUS,
    Choghadiya.SHUBH: TimingQuality.AUSPICIOUS,
    Choghadiya.LABH: TimingQuality.AUSPICIOUS,
    Choghadiya.CHAR: TimingQuality.NEUTRAL,
    Choghadiya.UDVEG: TimingQuality.INAUSPICIOUS,
    Choghadiya.KAAL: TimingQuality.INAUSPICIOUS,
    Choghadiya.ROG: TimingQuality.INAUSPICIOUS,
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
        """Query params for one local day at one place.

        The datetime MUST carry a UTC offset: Prokerala rejects a naive value
        with error 1003 ("Value should be a string in ISO 8601 … Example:
        2004-02-12T15:19:21+05:30"), verified against the live API. Attaching
        the offset ourselves from the IANA tzdb is the §5.2 rule anyway — we
        never let a vendor infer a timezone on our behalf.

        Sunrise-anchored day: we ask about the local morning, not midnight UTC,
        so the answer belongs to the date the user means (§5.3).
        """
        local_morning = dt.datetime.combine(on, dt.time(6, 0), tzinfo=ZoneInfo(place.tz))
        return {
            "ayanamsa": AYANAMSA_LAHIRI,
            "coordinates": f"{place.lat},{place.lon}",
            "datetime": local_morning.isoformat(),
            "la": "en",  # facts only; user-facing copy is ours (§2.4)
        }

    def _tithi_index(self, entry: dict) -> int:
        """Prokerala's tithi id → our 1-30 index.

        VERIFIED against the live API (2026-01-01, Mumbai): they return
        `id: 28, name: "Trayodashi", paksha: "Shukla Paksha"` for the tithi our
        engine independently computes as 13 (Shukla Trayodashi), with the two
        end instants agreeing to the second. So Prokerala numbers tithis
        KRISHNA-first (1-15 krishna, 16-30 shukla) where our contract is
        SHUKLA-first — a 15-place rotation.

        Do NOT use their `index` field: it is 0 on every entry we have seen.

        The paksha string is then re-derived and compared, so if they ever
        renumber, this surfaces as an outage rather than a silently wrong
        tithi — which would be a fabricated fact (§5.3).
        """
        raw_id = to_index(require(entry, "id"))
        if not 1 <= raw_id <= 30:
            raise ShapeError(f"tithi id out of range: {raw_id}")
        ours = ((raw_id + 14) % 30) + 1
        stated = str(pick(entry, "paksha") or "").strip().lower()
        if stated:
            expected = "shukla" if ours <= 15 else "krishna"
            if expected not in stated:
                raise ShapeError(
                    f"tithi id {raw_id} maps to {expected} paksha but the vendor "
                    f"says {stated!r} — their numbering may have changed"
                )
        return ours

    def _nakshatra_index(self, entry: dict) -> int:
        """Prokerala's nakshatra id → our 1-27 index.

        VERIFIED against the live API: `id: 3` is Rohini, which is the 4th
        nakshatra in the canonical Ashwini-first order — their ids are 0-based.
        """
        raw_id = to_index(require(entry, "id"))
        if not 0 <= raw_id <= 26:
            raise ShapeError(f"nakshatra id out of range: {raw_id}")
        return raw_id + 1

    async def panchang(self, query: PanchangQuery) -> NormalisedPanchang:
        raw = await self._get("panchang", self._base_params(query.place, query.local_date))
        tz = query.place.tz
        try:
            # Both come back as lists ordered by start; the first entry is the
            # one running at the queried instant (local sunrise-ish).
            tithi = require(raw, "data.tithi.0", "data.tithi")
            nakshatra = require(raw, "data.nakshatra.0", "data.nakshatra")
            return NormalisedPanchang(
                provider=self.name,
                local_date=query.local_date,
                sunrise_utc=to_utc(require(raw, "data.sunrise", "sunrise"), tz),
                sunset_utc=to_utc(require(raw, "data.sunset", "sunset"), tz),
                tithi=BoundaryReading(
                    index=self._tithi_index(tithi),
                    starts_utc=to_utc(require(tithi, "start", "starts_at"), tz),
                    ends_utc=to_utc(require(tithi, "end", "ends_at"), tz),
                ),
                nakshatra=BoundaryReading(
                    index=self._nakshatra_index(nakshatra),
                    starts_utc=to_utc(require(nakshatra, "start", "starts_at"), tz),
                    ends_utc=to_utc(require(nakshatra, "end", "ends_at"), tz),
                ),
            )
        except (ShapeError, ValueError) as exc:
            raise unparseable(self.name, str(exc)) from exc

    async def day_timings(self, query: PanchangQuery) -> NormalisedDayTimings:
        """Prokerala's choghadiya endpoint (VERIFIED against the live API).

        It returns `data.muhurat`: a flat list of sixteen entries, each with
        `name`, `is_day` and start/end — eight day parts then eight night ones.
        It does NOT return rahu kaal, yamaganda or gulikai, so those bands have
        no cross-check here and the Layer-D job compares what exists rather
        than inventing what does not (§5.3).

        We deliberately ignore their `type` field ("Good", "Most Auspicious",
        "Inauspicious"): it folds in vela overrides on top of the choghadiya
        name, so it is not comparable with ours. Quality is derived from the
        NAME on our side, consistently across providers.
        """
        raw = await self._get("day_timings", self._base_params(query.place, query.local_date))
        tz = query.place.tz
        windows: list[TimingWindow] = []
        try:
            entries = require(raw, "data.muhurat", "data.choghadiya", "muhurat")
            day_seen = night_seen = 0
            for entry in entries:
                name = _CHOGHADIYA_NAMES.get(
                    str(require(entry, "name")).strip().lower().replace(" ", "")
                )
                if name is None:
                    raise ShapeError(f"unknown choghadiya name: {entry.get('name')!r}")
                is_day = bool(pick(entry, "is_day"))
                if is_day:
                    day_seen += 1
                    position = day_seen
                else:
                    night_seen += 1
                    position = night_seen
                windows.append(
                    TimingWindow(
                        timing=(
                            DayTimingKind.CHOGHADIYA_DAY
                            if is_day
                            else DayTimingKind.CHOGHADIYA_NIGHT
                        ),
                        starts_utc=to_utc(require(entry, "start", "starts_at"), tz),
                        ends_utc=to_utc(require(entry, "end", "ends_at"), tz),
                        quality=_CHOGHADIYA_QUALITY[name],
                        choghadiya=name,
                        part_index=min(position, 8),
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
        """Prokerala has NO typed muhurat finder — verified against the live API.

        §5.2's provider table already recorded this ("Muhurat: not clearly
        itemised", against DivineAPI's "dedicated finder"); the live endpoint
        confirms it. `/v2/astrology/auspicious-period` ignores a `type`
        parameter entirely and returns the day's GENERIC auspicious periods —
        Abhijit Muhurat, Amrit Kaal, Brahma Muhurat.

        So a typed query is declined rather than answered. Returning Brahma
        Muhurat to someone asking when to hold a wedding would be a fabricated
        fact wearing the right label, which is precisely what §5.3 forbids.
        DivineAPI remains the only source for typed muhurat (§32.2).
        """
        if query.muhurat_type is not MuhuratType.GENERAL:
            raise unparseable(
                self.name,
                f"no typed muhurat finder — cannot answer {query.muhurat_type.value}",
            )

        raw = await self._get("muhurat", self._base_params(query.place, query.date_from))
        tz = query.place.tz
        try:
            entries = require(raw, "data.muhurat", "data.auspicious_period", "data.periods")
            windows = tuple(
                MuhuratWindow(
                    starts_utc=to_utc(require(period, "start", "starts_at"), tz),
                    ends_utc=to_utc(require(period, "end", "ends_at"), tz),
                    quality=TimingQuality.AUSPICIOUS,
                )
                # Each named period carries a LIST of occurrences.
                for entry in entries
                for period in require(entry, "period", "periods")
            )
        except (ShapeError, ValueError) as exc:
            raise unparseable(self.name, str(exc)) from exc
        return NormalisedMuhurat(
            provider=self.name, muhurat_type=query.muhurat_type, windows=windows
        )
