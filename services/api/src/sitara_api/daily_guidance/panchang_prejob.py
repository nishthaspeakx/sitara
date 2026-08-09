"""The 00:30 global panchang pre-job (§7.1, diagram 5's first box).

    "panchang facts (from `panchang_cache`, populated once per
    date+geohash+tradition by a global pre-job at 00:30 local-region time —
    thousands of users share one panchang doc)"

This is the single biggest cost lever in the morning pipeline and it works by
subtraction: the wave's per-user marginal cost is one Claude call and nothing
else, because by the time the wave runs every panchang document it needs is
already in the cache. Getting that wrong does not break the brief — the §8
ladder still fetches on demand — it just multiplies the vendor bill by the
number of users sharing each cell.

Two properties are load-bearing and neither is obvious:

* **The cell is the cache key, not the user.** §7.2's key is
  `panchang:{date}:{geohash4}:{tradition}:{provider}`; there is no user in it,
  by construction (`cache_keys.is_global_key`). The pre-job therefore works
  over DISTINCT CELLS, and a city of ten thousand users costs exactly what a
  city of one does. A pre-job that iterated users instead would produce
  identical output at ten thousand times the price, and nothing downstream
  would notice.

* **"00:30 local-region", not 00:30 UTC.** A region's cells are warmed just
  after ITS midnight, which is what puts them in place a few hours before that
  region's morning wave rather than after it. Regions are therefore scheduled
  by zone, and the Beat entry runs every half hour to catch whichever zones
  have just turned over.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from sitara_schemas.cache_keys import geohash
from sitara_schemas.facts import Tradition

from sitara_api.panchang.providers.base import ResolvedPlace
from sitara_api.panchang.providers.http import ProviderUnavailable

logger = logging.getLogger(__name__)

#: §7.1's "00:30 local-region time", in minutes past local midnight.
PREJOB_LOCAL_MINUTE = 30

#: How often the Beat entry fires. Every zone whose local clock crossed 00:30
#: within one of these windows is warmed exactly once.
PREJOB_TICK_MINUTES = 30


@dataclass(frozen=True)
class PanchangCell:
    """One shared document: a date, a ~20km geohash cell and a tradition.

    `place` carries a representative coordinate for the cell — the vendor needs
    a point, and every point inside a precision-4 geohash agrees to well within
    the tolerance §5.2 Layer D compares on.
    """

    local_date: dt.date
    geohash4: str
    tradition: Tradition
    place: ResolvedPlace

    @property
    def identity(self) -> tuple[str, str, str]:
        return (self.local_date.isoformat(), self.geohash4, self.tradition.value)


@dataclass(frozen=True)
class PrejobReport:
    warmed: int = 0
    already_cached: int = 0
    unavailable: int = 0
    cells: tuple[tuple[str, str, str], ...] = field(default_factory=tuple)

    def summary(self) -> str:
        return (
            f"cells={len(self.cells)} warmed={self.warmed} "
            f"cached={self.already_cached} unavailable={self.unavailable}"
        )


def cells_for(
    subjects: Iterable[tuple[float, float, str, Tradition]], local_date: dt.date
) -> list[PanchangCell]:
    """Collapse (lat, lon, tz, tradition) rows into DISTINCT shared cells.

    The collapse is the whole job. Ten thousand users in Mumbai produce one
    cell; a family split across Mumbai and Pune produce two, because they are
    two geohash cells and §5.2 computes sunrise for a place, not a country.
    """
    seen: dict[tuple[str, str], PanchangCell] = {}
    for lat, lon, tz, tradition in subjects:
        cell_hash = geohash(lat, lon)
        key = (cell_hash, tradition.value)
        if key in seen:
            continue
        seen[key] = PanchangCell(
            local_date=local_date,
            geohash4=cell_hash,
            tradition=tradition,
            place=ResolvedPlace(label=cell_hash, lat=lat, lon=lon, tz=tz),
        )
    return list(seen.values())


def zones_crossing_prejob_hour(
    zones: Iterable[str], now: dt.datetime, *, tick_minutes: int = PREJOB_TICK_MINUTES
) -> list[tuple[str, dt.date]]:
    """Zones whose local clock passed 00:30 inside this tick's window.

    Returns (zone, the local date to warm) — and the date warmed is the local
    date that has just STARTED, since 00:30 belongs to it. Warming yesterday
    would be perfectly consistent and completely useless.
    """
    window = dt.timedelta(minutes=tick_minutes)
    out: list[tuple[str, dt.date]] = []
    for zone_name in zones:
        zone = ZoneInfo(zone_name)
        local_now = now.astimezone(zone)
        local_prejob = local_now.replace(
            hour=0, minute=PREJOB_LOCAL_MINUTE, second=0, microsecond=0
        )
        if local_prejob <= local_now < local_prejob + window:
            out.append((zone_name, local_now.date()))
    return out


class PanchangPrejob:
    """Warms `panchang_cache` for a region's cells (§7.1).

    Failure is not fatal and must not be: §8's ladder means an unwarmed cell is
    fetched on demand during the wave, more slowly and more expensively but
    correctly. A pre-job that raised would take the morning down to save money.
    """

    def __init__(self, panchang_service, *, traditions: Sequence[Tradition] = ()) -> None:  # noqa: ANN001
        self._service = panchang_service
        self._traditions = tuple(traditions) or (Tradition.AMANTA, Tradition.PURNIMANTA)

    async def warm(self, cells: Sequence[PanchangCell]) -> PrejobReport:
        warmed = already = unavailable = 0
        touched: list[tuple[str, str, str]] = []

        for cell in cells:
            touched.append(cell.identity)
            try:
                result = await self._service.panchang(
                    cell.local_date, cell.place, cell.tradition
                )
            except ProviderUnavailable:
                # §8: the wave will try again on demand. Counted, not raised.
                unavailable += 1
                logger.warning(
                    "panchang pre-job cell unavailable",
                    extra={"cell": cell.identity},
                )
                continue
            if result.cached:
                already += 1
            else:
                warmed += 1

        report = PrejobReport(
            warmed=warmed,
            already_cached=already,
            unavailable=unavailable,
            cells=tuple(touched),
        )
        logger.info("panchang pre-job complete", extra={"report": report.summary()})
        return report
