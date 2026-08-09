"""Construction — the only place the morning pipeline's parts meet a config.

Kept apart from `service.py` so the service stays a pure composition of typed
collaborators, and apart from `tasks.py` so a Celery worker is not the only way
to build one. Everything here degrades rather than raises: §8's ladder is the
contract, and a missing provider key is "that rung is down", never a crash at
boot (the same rule the panchang module already follows for a blank vendor key).
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Awaitable, Callable, Sequence

from sitara_schemas.facts import ConfidenceState, Tradition

from sitara_api.chat_orchestration.config import ChatSettings
from sitara_api.daily_guidance.notify import NotificationQueue
from sitara_api.daily_guidance.polish import BriefPolisher
from sitara_api.daily_guidance.repository import (
    SCHEDULABLE_STATUSES,
    SubjectRepository,
    density_from,
)
from sitara_api.daily_guidance.service import (
    BriefFacts,
    BriefFactSource,
    DailyGuidanceService,
)
from sitara_api.daily_guidance.store import BriefStore
from sitara_api.daily_guidance.types import BriefSubject
from sitara_api.daily_guidance.windows import DEFAULT_BRIEF_TIME

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Facts
# ---------------------------------------------------------------------------


class CompositeBriefFacts(BriefFactSource):
    """§7.1's fact stage: "chart facts (cached, Layer A) → panchang facts".

    Both halves, and neither may take the other down. The two failure modes are
    genuinely independent — DivineAPI can be unreachable while our own engine is
    fine, and a user can have no birth time on a morning when every vendor is
    healthy — so each is fetched, each failure is NAMED in `missing`, and the
    brief degrades on whatever is left. That is what makes `degrade_reason`
    worth reading: "the panchang cell was cold" and "this person has no birth
    time" produce the same short brief and are not the same problem.

    Chart facts are also the half with a real cache behind it (§7.2: the natal
    chart is permanent until an engine bump), so the marginal cost of the chart
    half after a user's first morning is one transit call.
    """

    def __init__(self, panchang_service, place_resolver, astrology=None) -> None:  # noqa: ANN001
        self._panchang = panchang_service
        self._places = place_resolver
        self._astrology = astrology

    async def fetch(self, subject: BriefSubject, local_date: str) -> BriefFacts:
        snapshots: list = []
        missing: list[str] = []
        degraded = False
        confidence = ConfidenceState.VERIFIED

        panchang = await self._panchang_facts(subject, local_date)
        if panchang is None:
            missing.append("panchang")
            degraded = True
        else:
            snapshots.extend(panchang.facts)
            confidence = panchang.confidence
            degraded = degraded or panchang.degraded or panchang.disputed

        chart = await self._chart_facts(subject, local_date)
        if chart is None:
            missing.append("chart")
            # A brief without the personal chart is §5.4's tradition-based
            # state, not an approximation of a reading we did not do.
            confidence = ConfidenceState.TRADITION_BASED_GENERAL
        else:
            snapshots.extend(chart)

        if not snapshots:
            return BriefFacts(
                confidence=ConfidenceState.CANNOT_CALCULATE,
                missing=tuple(missing) or ("panchang", "chart"),
                degraded=True,
            )

        return BriefFacts(
            snapshots=tuple(snapshots),
            confidence=confidence,
            missing=tuple(missing),
            degraded=degraded,
        )

    async def _panchang_facts(self, subject: BriefSubject, local_date: str):  # noqa: ANN202
        from sitara_api.panchang.providers.base import ResolvedPlace
        from sitara_api.panchang.providers.http import ProviderUnavailable

        if self._panchang is None or subject.lat is None or subject.lon is None:
            return None
        place = ResolvedPlace(
            label=subject.timezone, lat=subject.lat, lon=subject.lon, tz=subject.timezone
        )
        try:
            return await self._panchang.panchang(
                dt.date.fromisoformat(local_date), place, Tradition.AMANTA
            )
        except ProviderUnavailable:
            logger.warning(
                "brief facts: panchang unavailable",
                extra={"user_id": subject.user_id, "local_date": local_date},
            )
            return None

    async def _chart_facts(self, subject: BriefSubject, local_date: str):  # noqa: ANN202
        from sitara_api.astrology.chart_adapter import (
            ChartEngineUnavailable,
            InsufficientBirthData,
        )

        if self._astrology is None:
            return None
        try:
            bundle = await self._astrology.chart_for(
                subject.user_id, local_date=local_date, timezone=subject.timezone
            )
        except InsufficientBirthData:
            # Not an outage. §28.2's missing-birth-time variant is the surface
            # that asks for it; the brief simply carries fewer cards today.
            logger.info(
                "brief facts: no chart — birth data insufficient",
                extra={"user_id": subject.user_id},
            )
            return None
        except ChartEngineUnavailable:
            logger.warning(
                "brief facts: chart engine unavailable",
                extra={"user_id": subject.user_id},
            )
            return None
        return bundle.all


#: M5's name for the panchang-only source. Kept so nothing that imported it
#: breaks; the composite is what `build_service` wires.
PanchangBriefFacts = CompositeBriefFacts


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def build_panchang_service(db):  # noqa: ANN001, ANN201
    """The §5.2 Layer-B service, assembled the same way `app.py` assembles it.

    Same parts, same order — the worker must not talk to a differently-wired
    provider stack than the API does, or a fact served in chat and the same
    fact in the morning brief could come from different rungs of the §8 ladder
    and disagree with each other in front of one user.
    """
    from sitara_api.config import Settings
    from sitara_api.panchang.adapter import AstroPanchangAdapter
    from sitara_api.panchang.cache import PanchangCache
    from sitara_api.panchang.registry import build_registry
    from sitara_api.panchang.service import PanchangService

    try:
        settings = Settings()
        registry = build_registry(settings)
        cache = PanchangCache(
            db,
            panchang_ttl_days=settings.panchang_cache_ttl_days,
            muhurat_ttl_days=settings.muhurat_cache_ttl_days,
        )
        return PanchangService(
            cache=cache,
            divineapi=registry.divineapi,
            prokerala=registry.prokerala,
            astro=AstroPanchangAdapter(
                settings.astro_base_url, settings.astro_timeout_seconds
            ),
        )
    except Exception:  # noqa: BLE001
        logger.warning("panchang service unavailable — brief facts will degrade (§8)")
        return None


async def build_astrology_facade(db, client=None):  # noqa: ANN001, ANN201
    """§13's single door to birth details, plus how to shut it.

    Returns `(facade, close)`, or `(None, noop)` when it cannot be built.

    CSFLE matters here more than anywhere else in the morning path: the birth
    row is marked "field-level: FULL doc payload" (§6.4), so a facade built
    without the codec would read ciphertext and hand the engine nonsense. When
    encryption is ON and the codec cannot be provisioned, this returns None —
    the brief then degrades with `missing=("chart",)` rather than composing a
    chart from garbage.

    The `close` half is not ceremony. `build_service` runs once per Celery
    `generate_brief` task — once per user per morning — and an earlier version
    opened a Mongo client here and never closed it, and provisioned a
    `FieldCrypto` whose own `close()` was never called. At Stage-2 volumes that
    is a hundred thousand leaked connection pools a day, on the one path that
    must not fall over at 06:00.
    """
    from sitara_api.astrology import AstroChartAdapter, AstrologyFacade
    from sitara_api.config import Settings
    from sitara_api.db.csfle import CsfleConfigurationError, build_crypto

    async def noop() -> None:
        return None

    settings = Settings()
    crypto = None
    if settings.csfle_enabled:
        if client is None:
            # The codec needs a CLIENT (for the key vault), not a database, and
            # opening a second one per task is what caused the leak. The caller
            # owns the connection and passes it in.
            logger.warning("CSFLE enabled but no client passed — skipping chart facts")
            return None, noop
        try:
            crypto = await build_crypto(client, settings)
        except CsfleConfigurationError:
            logger.warning("CSFLE unavailable — chart facts will be skipped (§13)")
            return None, noop

    facade = AstrologyFacade(
        db=db,
        adapter=AstroChartAdapter(
            settings.astro_base_url, settings.astro_timeout_seconds
        ),
        crypto=crypto,
    )

    async def close() -> None:
        if crypto is not None:
            await crypto.close()

    return facade, close


async def build_service(
    db,  # noqa: ANN001
    client=None,  # noqa: ANN001
) -> tuple[DailyGuidanceService, Callable[[], Awaitable[None]]]:
    """A ready service plus its teardown.

    The teardown is real work, not a placeholder: the CSFLE codec holds a
    key-vault connection, and this runs once per Celery task. `client` is the
    caller's Mongo client, borrowed for the key vault rather than opened again.
    """
    from sitara_api.panchang.places import GazetteerResolver

    panchang = build_panchang_service(db)
    astrology, close_astrology = await build_astrology_facade(db, client)
    facts: BriefFactSource
    if panchang is None and astrology is None:
        facts = _NoFacts()
    else:
        facts = CompositeBriefFacts(panchang, GazetteerResolver(), astrology)

    polisher = None
    chat_settings = ChatSettings()
    if chat_settings.anthropic_api_key:
        from sitara_api.chat_orchestration.llm import build_llm

        polisher = BriefPolisher(build_llm(chat_settings), settings=chat_settings)
    else:
        # §7.1's cost lever is also the no-key path: ranking-only briefs are a
        # first-class product state, so a deployment without a model key still
        # produces a real, verified brief every morning.
        logger.info("no model key — briefs will ship ranking-only (§7.1 cost lever)")

    service = DailyGuidanceService(
        facts=facts,
        store=BriefStore(db),
        queue=NotificationQueue(db),
        polisher=polisher,
    )

    async def close() -> None:
        await close_astrology()

    return service, close


class _NoFacts(BriefFactSource):
    async def fetch(self, subject: BriefSubject, local_date: str) -> BriefFacts:
        return BriefFacts(
            confidence=ConfidenceState.CANNOT_CALCULATE,
            missing=("panchang", "chart"),
            degraded=True,
        )


# ---------------------------------------------------------------------------
# Loading one subject (the per-user task's entry point)
# ---------------------------------------------------------------------------


async def load_subject(db, user_id: str) -> BriefSubject | None:  # noqa: ANN001
    """Rebuild one `BriefSubject` at generation time.

    Deliberately re-read rather than carried through the queue: between the
    tick that selected this user and the worker that generates for them lie up
    to ninety minutes, and §32.7's locale change is exactly the event that
    happens inside that gap. Reading now means the brief is composed in the
    language the user has NOW, which is the outcome §2.4 requires and the one a
    serialised snapshot would quietly miss.
    """
    from bson import ObjectId

    from sitara_api.daily_guidance.priority import Entitlement, tier_for

    oid = ObjectId(user_id)
    user = await db.users.find_one({"_id": oid})
    if user is None or user.get("status") not in SCHEDULABLE_STATUSES:
        return None
    profile = await db.profiles.find_one({"user_id": oid}) or {}
    subscription = (
        await db.subscriptions.find_one({"user_id": oid}, sort=[("created_at", -1)]) or {}
    )
    if not user.get("timezone") or not user.get("locale"):
        return None

    return BriefSubject(
        user_id=user_id,
        locale=user["locale"],
        timezone=user["timezone"],
        brief_time=profile.get("brief_time") or DEFAULT_BRIEF_TIME,
        density=density_from(profile.get("density")),
        tier=tier_for(
            Entitlement(
                plan=subscription.get("plan"),
                status=subscription.get("status"),
                trial_ends_at=subscription.get("trial_ends_at"),
            ),
            now=dt.datetime.now(dt.UTC),
        ),
        follow_timezone=profile.get("follow_timezone", True),
        lat=(profile.get("brief_place") or {}).get("lat"),
        lon=(profile.get("brief_place") or {}).get("lon"),
    )


async def subject_places(
    db, timezone: str  # noqa: ANN001
) -> list[tuple[float, float, str, Tradition]]:
    """Every (lat, lon, tz, tradition) in one zone — the pre-job's input.

    Returned unaggregated; `panchang_prejob.cells_for` does the collapse into
    distinct geohash cells, which is where that logic belongs and where it is
    tested.
    """
    rows: list[tuple[float, float, str, Tradition]] = []
    cursor = db.users.aggregate(
        [
            {"$match": {"timezone": timezone, "status": {"$in": list(SCHEDULABLE_STATUSES)}}},
            {
                "$lookup": {
                    "from": "profiles",
                    "localField": "_id",
                    "foreignField": "user_id",
                    "as": "profile",
                }
            },
            {"$unwind": "$profile"},
            {"$project": {"profile.brief_place": 1, "timezone": 1}},
        ]
    )
    async for doc in cursor:
        place = (doc.get("profile") or {}).get("brief_place") or {}
        if place.get("lat") is None or place.get("lon") is None:
            continue
        rows.append((place["lat"], place["lon"], doc["timezone"], Tradition.AMANTA))
    return rows


def repository(db) -> SubjectRepository:  # noqa: ANN001
    return SubjectRepository(db)


def subjects_for_zone(places: Sequence[tuple[float, float, str, Tradition]]) -> int:
    return len(places)
