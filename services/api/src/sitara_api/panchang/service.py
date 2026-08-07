"""Panchang orchestration — the §8 degradation ladder, in order.

    cache (DivineAPI) → DivineAPI → internal Layer A → Prokerala → decline

§8 states the rungs: "DivineAPI down → internal panchang (if within validated
scope) or Prokerala; cross-source disputed → confidence downgrade + neutral
framing; unverifiable calculation → no personalised guidance". Each step down
costs confidence, and the last one is an honest decline rather than a guess
(§5.3).

Only DivineAPI results are ever written to the cache: Prokerala is ephemeral by
ToS, and Layer-A fallbacks are recomputed on demand rather than becoming a
system of record for calendar facts.
"""

import datetime as dt
import logging
from dataclasses import dataclass, field

from sitara_schemas.cache_keys import muhurat_key, panchang_key
from sitara_schemas.facts import ConfidenceState, FactSnapshot, FactSource, MuhuratType, Tradition

from sitara_api.panchang import factbuild
from sitara_api.panchang.adapter import AstroPanchangAdapter
from sitara_api.panchang.cache import (
    CACHE_KIND_MUHURAT,
    CACHE_KIND_PANCHANG,
    PanchangCache,
)
from sitara_api.panchang.providers.base import (
    MuhuratQuery,
    PanchangProvider,
    PanchangQuery,
    ProviderName,
    ResolvedPlace,
)
from sitara_api.panchang.providers.http import ProviderUnavailable, engine_unavailable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PanchangResult:
    """What the endpoints return. `sources` is plural because the Trust Sheet
    says "verified against 2 independent sources" (§13) — it must be able to
    name them."""

    facts: list[FactSnapshot]
    confidence: ConfidenceState
    sources: tuple[FactSource, ...]
    place: ResolvedPlace
    disputed: bool = False
    cached: bool = False
    degraded: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)


class PanchangService:
    def __init__(
        self,
        cache: PanchangCache,
        divineapi: PanchangProvider | None,
        prokerala: PanchangProvider | None,
        astro: AstroPanchangAdapter | None,
    ) -> None:
        self._cache = cache
        self._divineapi = divineapi
        self._prokerala = prokerala
        self._astro = astro

    # ---- panchang -------------------------------------------------------

    async def panchang(
        self, local_date: dt.date, place: ResolvedPlace, tradition: Tradition
    ) -> PanchangResult:
        """§32.2 authority, applied per fact class (decision D1).

        Two sources are combined rather than raced:

        * The tithi/nakshatra BOUNDARY INSTANTS are deterministic astronomy, so
          Layer A is authoritative and its values replace the vendor's wherever
          our engine can answer. §32.2's closing line is the whole point: two
          unverified vendors can never overrule validated astronomy — and a
          vendor cannot do it merely by being the one we happened to call.
        * The calendar layer stays DivineAPI-primary, cached as the §6.4 row.

        The ladder below only decides who supplies the CALENDAR layer; Layer A
        is consulted independently and is never a rung on it.
        """
        vendor = await self._vendor_panchang(local_date, place, tradition)
        layer_a = None
        if self._astro is not None:
            layer_a = await self._astro.panchang(
                local_date, place, tradition, include_day_timings=False
            )

        if vendor is None and not layer_a:
            raise engine_unavailable()

        if vendor is None:
            # Calendar sources are all down; the astronomy still stands.
            assert layer_a is not None
            return PanchangResult(
                facts=layer_a,
                confidence=ConfidenceState.TRADITION_BASED_GENERAL,
                sources=(FactSource.LAYER_A,),
                place=place,
                degraded=True,
                notes=("calendar_sources_unavailable",),
            )

        if not layer_a:
            return vendor

        # Layer A wins on the facts it owns; the vendor keeps the rest.
        authoritative = {f.kind for f in layer_a}
        merged = layer_a + [f for f in vendor.facts if f.kind not in authoritative]
        if vendor.disputed:
            merged = [f.model_copy(update={"confidence": vendor.confidence}) for f in merged]
        return PanchangResult(
            facts=merged,
            confidence=vendor.confidence,
            sources=(FactSource.LAYER_A, *vendor.sources),
            place=place,
            disputed=vendor.disputed,
            cached=vendor.cached,
            degraded=vendor.degraded,
            notes=vendor.notes,
        )

    async def _vendor_panchang(
        self, local_date: dt.date, place: ResolvedPlace, tradition: Tradition
    ) -> PanchangResult | None:
        """The calendar layer: cache → DivineAPI → Prokerala. None if all down."""
        key = panchang_key(
            local_date, place.lat, place.lon, tradition, ProviderName.DIVINEAPI.value
        )
        query = PanchangQuery(local_date=local_date, place=place, tradition=tradition)

        cached = await self._cache.get(key)
        if cached is not None:
            return self._from_cache(cached, place, tradition)

        if self._divineapi is not None:
            try:
                reading = await self._divineapi.panchang(query)
            except ProviderUnavailable as exc:
                logger.info("divineapi unavailable (%s) — descending the ladder", exc.reason)
            else:
                facts = factbuild.panchang_facts(reading, place, tradition)
                await self._cache.put(
                    key,
                    kind=CACHE_KIND_PANCHANG,
                    local_date=local_date,
                    place=place,
                    tradition=tradition,
                    provider=ProviderName.DIVINEAPI,
                    payload={"facts": [f.model_dump(mode="json") for f in facts]},
                )
                return PanchangResult(
                    facts=facts,
                    confidence=ConfidenceState.TRADITION_BASED_GENERAL,
                    sources=(FactSource.DIVINEAPI,),
                    place=place,
                )

        # Prokerala — served, never stored (ToS), confidence downgraded.
        if self._prokerala is not None:
            try:
                reading = await self._prokerala.panchang(query)
            except ProviderUnavailable as exc:
                logger.info("prokerala unavailable (%s)", exc.reason)
            else:
                return PanchangResult(
                    facts=factbuild.panchang_facts(
                        reading, place, tradition, confidence=ConfidenceState.APPROXIMATE
                    ),
                    confidence=ConfidenceState.APPROXIMATE,
                    sources=(FactSource.PROKERALA,),
                    place=place,
                    degraded=True,
                    notes=("degraded_to_prokerala", "never_cached_tos"),
                )

        return None

    # ---- day timings ----------------------------------------------------

    async def day_timings(
        self, local_date: dt.date, place: ResolvedPlace, tradition: Tradition
    ) -> PanchangResult:
        query = PanchangQuery(local_date=local_date, place=place, tradition=tradition)

        if self._divineapi is not None:
            try:
                reading = await self._divineapi.day_timings(query)
            except ProviderUnavailable as exc:
                logger.info("divineapi day timings unavailable (%s)", exc.reason)
            else:
                return PanchangResult(
                    facts=factbuild.day_timing_facts(reading, place, tradition),
                    confidence=ConfidenceState.TRADITION_BASED_GENERAL,
                    sources=(FactSource.DIVINEAPI,),
                    place=place,
                )

        if self._astro is not None:
            facts = await self._astro.panchang(
                local_date, place, tradition, include_day_timings=True
            )
            if facts:
                timings = [f for f in facts if f.kind.value == "panchang.day_timing"]
                if timings:
                    return PanchangResult(
                        facts=timings,
                        confidence=ConfidenceState.TRADITION_BASED_GENERAL,
                        sources=(FactSource.LAYER_A,),
                        place=place,
                        degraded=True,
                        notes=("degraded_to_layer_a",),
                    )

        if self._prokerala is not None:
            try:
                reading = await self._prokerala.day_timings(query)
            except ProviderUnavailable as exc:
                logger.info("prokerala day timings unavailable (%s)", exc.reason)
            else:
                return PanchangResult(
                    facts=factbuild.day_timing_facts(
                        reading, place, tradition, confidence=ConfidenceState.APPROXIMATE
                    ),
                    confidence=ConfidenceState.APPROXIMATE,
                    sources=(FactSource.PROKERALA,),
                    place=place,
                    degraded=True,
                    notes=("degraded_to_prokerala", "never_cached_tos"),
                )

        raise engine_unavailable()

    # ---- muhurat --------------------------------------------------------

    async def muhurat(
        self,
        muhurat_type: MuhuratType,
        date_from: dt.date,
        date_to: dt.date,
        place: ResolvedPlace,
        tradition: Tradition,
    ) -> PanchangResult:
        """§30.2: computed for THAT place, in its timezone, labelled with its
        city. There is no internal rung — muhurat finding is a DivineAPI
        capability we do not reimplement (§5.2), so below it we decline."""
        key = muhurat_key(muhurat_type, date_from, date_to, place.lat, place.lon)
        query = MuhuratQuery(
            muhurat_type=muhurat_type,
            date_from=date_from,
            date_to=date_to,
            place=place,
            tradition=tradition,
        )

        cached = await self._cache.get(key)
        if cached is not None:
            return self._from_cache(cached, place, tradition, kind=CACHE_KIND_MUHURAT)

        if self._divineapi is not None:
            try:
                reading = await self._divineapi.muhurat(query)
            except ProviderUnavailable as exc:
                logger.info("divineapi muhurat unavailable (%s)", exc.reason)
            else:
                facts = factbuild.muhurat_facts(reading, place, tradition, date_from)
                await self._cache.put(
                    key,
                    kind=CACHE_KIND_MUHURAT,
                    local_date=date_from,
                    place=place,
                    tradition=tradition,
                    provider=ProviderName.DIVINEAPI,
                    payload={"facts": [f.model_dump(mode="json") for f in facts]},
                )
                return PanchangResult(
                    facts=facts,
                    confidence=ConfidenceState.TRADITION_BASED_GENERAL,
                    sources=(FactSource.DIVINEAPI,),
                    place=place,
                )

        if self._prokerala is not None:
            try:
                reading = await self._prokerala.muhurat(query)
            except ProviderUnavailable as exc:
                logger.info("prokerala muhurat unavailable (%s)", exc.reason)
            else:
                return PanchangResult(
                    facts=factbuild.muhurat_facts(
                        reading,
                        place,
                        tradition,
                        date_from,
                        confidence=ConfidenceState.APPROXIMATE,
                    ),
                    confidence=ConfidenceState.APPROXIMATE,
                    sources=(FactSource.PROKERALA,),
                    place=place,
                    degraded=True,
                    notes=("degraded_to_prokerala", "never_cached_tos"),
                )

        raise engine_unavailable()

    # ---- helpers --------------------------------------------------------

    def _from_cache(
        self,
        document: dict,
        place: ResolvedPlace,
        tradition: Tradition,
        kind: str = CACHE_KIND_PANCHANG,
    ) -> PanchangResult:
        facts = [FactSnapshot.model_validate(f) for f in document["payload"]["facts"]]
        disputed = bool(document.get("disputed"))
        # §32.2: a disputed fact keeps serving from DivineAPI, with confidence
        # downgraded — §5.4's "disputed fact in play" row.
        confidence = (
            ConfidenceState.APPROXIMATE if disputed else ConfidenceState.TRADITION_BASED_GENERAL
        )
        if disputed:
            facts = [f.model_copy(update={"confidence": confidence}) for f in facts]
        return PanchangResult(
            facts=facts,
            confidence=confidence,
            sources=(FactSource.DIVINEAPI,),
            place=place,
            disputed=disputed,
            cached=True,
        )
