"""Layer D — the nightly comparison engine (SPEC §5.2, §32.2).

"nightly job diffs internal engine vs DivineAPI vs Prokerala on a rolling
sample (500 users' next-day data + the golden set slice); any discrepancy
beyond tolerance → admin alert + [§32.2's authority rules] + the affected fact
is flagged `disputed`."

The comparison itself is pure (adjudicate.py); this module is the IO shell:
gather three readings, adjudicate, persist. It reads no user records — the
sample is a list of date+place+tradition triples, because panchang is global
(§34.2) and comparing it needs nobody's identity.

Scheduling is Celery Beat's job from M5; today this runs from the CLI:

    uv run python -m sitara_api.panchang.compare_job --sample 20 --dry-run
"""

import argparse
import asyncio
import datetime as dt
import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from sitara_schemas.cache_keys import panchang_key
from sitara_schemas.facts import FactKind, FactSource, Tradition

from sitara_api.panchang.adjudicate import (
    BOUNDARY_TOLERANCE,
    Adjudication,
    FactClass,
    Reading,
    adjudicate,
)
from sitara_api.panchang.cache import PanchangCache
from sitara_api.panchang.providers.base import (
    NormalisedPanchang,
    PanchangProvider,
    PanchangQuery,
    ProviderName,
    ResolvedPlace,
)
from sitara_api.panchang.providers.http import ProviderUnavailable

logger = logging.getLogger(__name__)

# What we compare, and under which §32.2 authority rule. Boundary instants are
# deterministic astronomy (decision D1) — Layer A authoritative, vendors flag
# review only. Sunrise likewise.
COMPARED_FACTS: tuple[tuple[str, FactClass], ...] = (
    ("tithi.ends_utc", FactClass.PANCHANG_ASTRONOMY),
    ("nakshatra.ends_utc", FactClass.PANCHANG_ASTRONOMY),
    ("sunrise_utc", FactClass.PANCHANG_ASTRONOMY),
)


@dataclass(frozen=True)
class SampleItem:
    local_date: dt.date
    place: ResolvedPlace
    tradition: Tradition = Tradition.AMANTA

    @property
    def cache_key(self) -> str:
        return panchang_key(
            self.local_date,
            self.place.lat,
            self.place.lon,
            self.tradition,
            ProviderName.DIVINEAPI.value,
        )


@dataclass
class ComparisonReport:
    sampled: int = 0
    compared: int = 0
    agreed: int = 0
    review_flagged: int = 0
    disputed: int = 0
    adjudications_queued: int = 0
    unreachable: dict[str, int] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "sampled": self.sampled,
            "compared": self.compared,
            "agreed": self.agreed,
            "review_flagged": self.review_flagged,
            "disputed": self.disputed,
            "adjudications_queued": self.adjudications_queued,
            "unreachable": self.unreachable,
            "skipped": self.skipped,
        }


def _reading(source: FactSource, value: dt.datetime | None) -> Reading | None:
    return None if value is None else Reading(source=source, instant=value)


def _extract(panchang: NormalisedPanchang | None, path: str) -> dt.datetime | None:
    if panchang is None:
        return None
    cursor: Any = panchang
    for part in path.split("."):
        cursor = getattr(cursor, part, None)
        if cursor is None:
            return None
    return cursor


def _layer_a_value(facts: Sequence[Any] | None, path: str) -> dt.datetime | None:
    """Pull the comparable instant out of Layer A's FactSnapshots."""
    if not facts:
        return None
    wanted = {
        "tithi.ends_utc": (FactKind.PANCHANG_TITHI_BOUNDARY, "ends_utc"),
        "nakshatra.ends_utc": (FactKind.PANCHANG_NAKSHATRA_BOUNDARY, "ends_utc"),
        "sunrise_utc": (FactKind.PANCHANG_SUNRISE_SUNSET, "sunrise_utc"),
    }[path]
    kind, attribute = wanted
    for fact in facts:
        if fact.kind is kind:
            return getattr(fact.value, attribute, None)
    return None


class ComparisonJob:
    def __init__(
        self,
        cache: PanchangCache,
        divineapi: PanchangProvider | None,
        prokerala: PanchangProvider | None,
        astro: Any | None,
        db: Any | None = None,
    ) -> None:
        self._cache = cache
        self._divineapi = divineapi
        self._prokerala = prokerala
        self._astro = astro
        self._db = db

    async def run(
        self, sample: Iterable[SampleItem], *, dry_run: bool = False
    ) -> ComparisonReport:
        report = ComparisonReport()
        for item in sample:
            report.sampled += 1
            await self._compare_one(item, report, dry_run=dry_run)
        logger.info("layer-d comparison complete: %s", report.as_dict())
        return report

    async def _compare_one(
        self, item: SampleItem, report: ComparisonReport, *, dry_run: bool
    ) -> None:
        query = PanchangQuery(
            local_date=item.local_date, place=item.place, tradition=item.tradition
        )
        divine = await self._fetch(self._divineapi, query, report)
        prokerala = await self._fetch(self._prokerala, query, report)
        layer_a = None
        if self._astro is not None:
            layer_a = await self._astro.panchang(
                item.local_date, item.place, item.tradition, include_day_timings=False
            )
            if not layer_a:
                report.unreachable["layer_a"] = report.unreachable.get("layer_a", 0) + 1

        if divine is None and prokerala is None and not layer_a:
            report.skipped.append(f"{item.local_date}:{item.place.label}:no sources")
            return

        for path, fact_class in COMPARED_FACTS:
            outcome = adjudicate(
                fact_class,
                layer_a=_reading(FactSource.LAYER_A, _layer_a_value(layer_a, path)),
                divineapi=_reading(FactSource.DIVINEAPI, _extract(divine, path)),
                prokerala=_reading(FactSource.PROKERALA, _extract(prokerala, path)),
                fact_key=f"{item.cache_key}#{path}",
                tolerance=BOUNDARY_TOLERANCE,
            )
            await self._record(item, path, outcome, report, dry_run=dry_run)

    async def _fetch(
        self, provider: PanchangProvider | None, query: PanchangQuery, report: ComparisonReport
    ) -> NormalisedPanchang | None:
        if provider is None:
            return None
        try:
            return await provider.panchang(query)
        except ProviderUnavailable as exc:
            name = provider.name.value
            report.unreachable[name] = report.unreachable.get(name, 0) + 1
            logger.info("layer-d: %s unavailable (%s)", name, exc.reason)
            return None

    async def _record(
        self,
        item: SampleItem,
        path: str,
        outcome: Adjudication,
        report: ComparisonReport,
        *,
        dry_run: bool,
    ) -> None:
        report.compared += 1
        if not outcome.review_flagged and not outcome.disputed:
            report.agreed += 1
            return

        if outcome.review_flagged:
            report.review_flagged += 1
        if outcome.disputed:
            report.disputed += 1

        if outcome.adjudication is None:
            # A chart-class flag: an admin signal for the §12 dashboard, not a
            # question for the Jyotish lead — our engine is already the answer.
            logger.warning(
                "layer-d review flag: %s %s (served %s)",
                item.place.label,
                path,
                outcome.source.value if outcome.source else "none",
            )
            return

        report.adjudications_queued += 1
        if dry_run or self._db is None:
            return

        document = outcome.adjudication.to_document()
        document["created_at"] = dt.datetime.now(dt.UTC)
        document["place_label"] = item.place.label
        document["local_date"] = item.local_date.isoformat()
        result = await self._db.fact_adjudications.insert_one(document)
        # §32.2: the fact keeps serving from DivineAPI, flagged so guidance
        # built on it downgrades its confidence (§5.4).
        await self._cache.mark_disputed(item.cache_key, adjudication_id=result.inserted_id)


def next_day_sample(cities: Sequence[ResolvedPlace], on: dt.date, limit: int) -> list[SampleItem]:
    """§5.2's "500 users' next-day data" without reading a single user record.

    Users are not the unit of comparison — date+place+tradition is, because
    panchang is global (§34.2). Sampling places covers every user in them.
    """
    return [SampleItem(local_date=on, place=place) for place in cities[:limit]]


async def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Layer-D nightly comparison (§5.2, §32.2)")
    parser.add_argument("--sample", type=int, default=20, help="how many places to compare")
    parser.add_argument("--date", type=dt.date.fromisoformat, default=None, help="local date")
    parser.add_argument(
        "--dry-run", action="store_true", help="compare and report; queue nothing"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from sitara_api.config import Settings
    from sitara_api.db import make_mongo
    from sitara_api.panchang.adapter import AstroPanchangAdapter
    from sitara_api.panchang.places import default_resolver
    from sitara_api.panchang.registry import build_registry

    settings = Settings()
    client, db = make_mongo(settings)
    registry = build_registry(settings)
    resolver = default_resolver()
    on = args.date or (dt.date.today() + dt.timedelta(days=1))

    job = ComparisonJob(
        cache=PanchangCache(db),
        divineapi=registry.divineapi,
        prokerala=registry.prokerala,
        astro=AstroPanchangAdapter(settings.astro_base_url, settings.astro_timeout_seconds),
        db=db,
    )
    sample = next_day_sample([c.to_place() for c in resolver.cities], on, args.sample)
    try:
        report = await job.run(sample, dry_run=args.dry_run)
    finally:
        client.close()

    print(report.as_dict())
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(_main(argv))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
