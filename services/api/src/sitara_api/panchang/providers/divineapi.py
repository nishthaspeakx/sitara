"""DivineAPI adapter — SPEC §5.2 Layer B PRIMARY.

"DivineAPI Vedic Ananta from W3, upgraded to Prakash when Tamil/Telugu wave
enters build (regional festival calendars + gowri panchangam)."

⚠️ SHAPE STATUS: the request paths and response field names below are the
adapter's ASSUMPTION, not a verified contract — they have not yet been checked
against a live trial account. `python -m sitara_api.panchang.record` makes one
real call per endpoint and writes the true payloads to
tests/panchang/fixtures/divineapi/; the assumptions here are corrected against
those fixtures, and the contract tests then pin the corrected shape forever.

Every field is read through `pick()` with several candidate paths, and anything
unrecognised raises rather than being half-understood: serving a timing we
cannot vouch for would break cite-or-die (§5.3).
"""

import datetime as dt

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
    VendorClient,
    unparseable,
)
from sitara_api.panchang.providers.parsing import ShapeError, pick, require, to_index, to_utc

# Overridable from settings so a corrected path never needs a code change.
DEFAULT_PATHS = {
    "panchang": "/indian-api/v1/panchang",
    "day_timings": "/indian-api/v1/choghadiya",
    "muhurat": "/indian-api/v1/muhurat",
}

_INAUSPICIOUS_BANDS = {
    "rahu_kaal": DayTimingKind.RAHU_KAAL,
    "rahukaal": DayTimingKind.RAHU_KAAL,
    "rahu_kalam": DayTimingKind.RAHU_KAAL,
    "yamaganda": DayTimingKind.YAMAGANDA,
    "yamagandam": DayTimingKind.YAMAGANDA,
    "gulikai": DayTimingKind.GULIKAI,
    "gulika": DayTimingKind.GULIKAI,
}


class DivineApiProvider:
    """Primary source for panchang, muhurat and festival facts (§32.2)."""

    name = ProviderName.DIVINEAPI

    def __init__(
        self,
        client: VendorClient,
        api_key: str | None,
        auth_token: str | None,
        paths: dict[str, str] | None = None,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._auth_token = auth_token
        self._paths = {**DEFAULT_PATHS, **(paths or {})}

    def _credentials(self) -> tuple[str, str]:
        if not self._api_key or not self._auth_token:
            # Missing key behaves exactly like an outage so the §8 ladder runs
            # (this is the playbook's kill-the-key acceptance).
            raise ProviderMisconfigured(self.name, "DIVINEAPI_API_KEY/AUTH_TOKEN not configured")
        return self._api_key, self._auth_token

    async def _call(self, path_key: str, query: PanchangQuery | MuhuratQuery, **extra):  # noqa: ANN003, ANN202
        api_key, auth_token = self._credentials()
        place = query.place
        body = {
            "api_key": api_key,
            "lat": place.lat,
            "lon": place.lon,
            "tzone": _tz_offset_hours(place.tz, _query_date(query)),
            "lang": "en",  # facts only; all user-facing copy is ours (§2.4)
            **extra,
        }
        return await self._client.request(
            "POST",
            self._paths[path_key],
            data=body,
            headers={"Authorization": f"Bearer {auth_token}"},
        )

    async def panchang(self, query: PanchangQuery) -> NormalisedPanchang:
        raw = await self._call(
            "panchang",
            query,
            date=query.local_date.isoformat(),
            day=query.local_date.day,
            month=query.local_date.month,
            year=query.local_date.year,
        )
        tz = query.place.tz
        try:
            return NormalisedPanchang(
                provider=self.name,
                local_date=query.local_date,
                sunrise_utc=to_utc(require(raw, "data.sunrise", "sunrise"), tz),
                sunset_utc=to_utc(require(raw, "data.sunset", "sunset"), tz),
                tithi=BoundaryReading(
                    index=to_index(
                        require(
                            raw, "data.tithi.number", "data.tithi.index", "tithi.number"
                        )
                    ),
                    starts_utc=to_utc(require(raw, "data.tithi.start", "tithi.start"), tz),
                    ends_utc=to_utc(require(raw, "data.tithi.end", "tithi.end"), tz),
                ),
                nakshatra=BoundaryReading(
                    index=to_index(
                        require(
                            raw,
                            "data.nakshatra.number",
                            "data.nakshatra.index",
                            "nakshatra.number",
                        )
                    ),
                    starts_utc=to_utc(require(raw, "data.nakshatra.start", "nakshatra.start"), tz),
                    ends_utc=to_utc(require(raw, "data.nakshatra.end", "nakshatra.end"), tz),
                ),
            )
        except (ShapeError, ValueError) as exc:
            raise unparseable(self.name, str(exc)) from exc

    async def day_timings(self, query: PanchangQuery) -> NormalisedDayTimings:
        raw = await self._call(
            "day_timings",
            query,
            date=query.local_date.isoformat(),
            day=query.local_date.day,
            month=query.local_date.month,
            year=query.local_date.year,
        )
        tz = query.place.tz
        windows: list[TimingWindow] = []
        try:
            for field, kind in _INAUSPICIOUS_BANDS.items():
                band = pick(raw, f"data.{field}", field)
                if band is None:
                    continue
                windows.append(
                    TimingWindow(
                        timing=kind,
                        starts_utc=to_utc(require(band, "start", "from"), tz),
                        ends_utc=to_utc(require(band, "end", "to"), tz),
                        quality=TimingQuality.INAUSPICIOUS,
                    )
                )
            windows.extend(self._parse_choghadiya(raw, tz))
        except (ShapeError, ValueError) as exc:
            raise unparseable(self.name, str(exc)) from exc

        if not windows:
            raise unparseable(self.name, "no recognisable day timings")
        return NormalisedDayTimings(
            provider=self.name, local_date=query.local_date, windows=tuple(windows)
        )

    def _parse_choghadiya(self, raw, tz: str):  # noqa: ANN001, ANN202
        from sitara_schemas.facts import Choghadiya

        quality_by_name = {
            Choghadiya.AMRIT: TimingQuality.AUSPICIOUS,
            Choghadiya.SHUBH: TimingQuality.AUSPICIOUS,
            Choghadiya.LABH: TimingQuality.AUSPICIOUS,
            Choghadiya.CHAR: TimingQuality.NEUTRAL,
            Choghadiya.UDVEG: TimingQuality.INAUSPICIOUS,
            Choghadiya.KAAL: TimingQuality.INAUSPICIOUS,
            Choghadiya.ROG: TimingQuality.INAUSPICIOUS,
        }
        for section, kind in (
            ("day", DayTimingKind.CHOGHADIYA_DAY),
            ("night", DayTimingKind.CHOGHADIYA_NIGHT),
        ):
            entries = pick(raw, f"data.choghadiya.{section}", f"choghadiya.{section}") or []
            for position, entry in enumerate(entries, start=1):
                label = str(require(entry, "name", "type")).strip().lower()
                try:
                    name = Choghadiya(label)
                except ValueError as exc:
                    raise ShapeError(f"unknown choghadiya name: {label!r}") from exc
                yield TimingWindow(
                    timing=kind,
                    starts_utc=to_utc(require(entry, "start", "from"), tz),
                    ends_utc=to_utc(require(entry, "end", "to"), tz),
                    quality=quality_by_name[name],
                    choghadiya=name,
                    part_index=min(position, 8),
                )

    async def muhurat(self, query: MuhuratQuery) -> NormalisedMuhurat:
        raw = await self._call(
            "muhurat",
            query,
            type=query.muhurat_type.value,
            date_from=query.date_from.isoformat(),
            date_to=query.date_to.isoformat(),
        )
        tz = query.place.tz
        try:
            entries = require(raw, "data.muhurat", "data.windows", "muhurat")
            windows = tuple(
                MuhuratWindow(
                    starts_utc=to_utc(require(entry, "start", "from"), tz),
                    ends_utc=to_utc(require(entry, "end", "to"), tz),
                    quality=TimingQuality.AUSPICIOUS,
                )
                for entry in entries
            )
        except (ShapeError, ValueError) as exc:
            raise unparseable(self.name, str(exc)) from exc
        return NormalisedMuhurat(
            provider=self.name, muhurat_type=query.muhurat_type, windows=windows
        )


def _query_date(query: PanchangQuery | MuhuratQuery) -> dt.date:
    return getattr(query, "local_date", None) or query.date_from  # type: ignore[union-attr]


def _tz_offset_hours(tz: str, on: dt.date) -> float:
    """Vendors want a numeric UTC offset. We compute it from the IANA tzdb for
    the queried DATE — a fixed constant would break across a DST change (§5.5)."""
    from zoneinfo import ZoneInfo

    noon = dt.datetime.combine(on, dt.time(12, 0), tzinfo=ZoneInfo(tz))
    offset = noon.utcoffset()
    assert offset is not None
    return offset.total_seconds() / 3600
