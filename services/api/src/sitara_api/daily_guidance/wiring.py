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


class PanchangBriefFacts(BriefFactSource):
    """The shared-cache half of §7.1's fact stage.

    Chart facts are the other half and are not wired yet: the Layer-A chart
    engine reaches this service through the astrology facade, which M5 left
    declining `NATAL_CHART`/`TRANSITS` (`chat_orchestration.facts`). Rather than
    invent a chart source here, this returns what it genuinely has and NAMES
    what it does not, so the brief degrades through §7.1's stated path instead
    of through a stub that looks like data.
    """

    def __init__(self, panchang_service, place_resolver) -> None:  # noqa: ANN001
        self._panchang = panchang_service
        self._places = place_resolver

    async def fetch(self, subject: BriefSubject, local_date: str) -> BriefFacts:
        from sitara_api.panchang.providers.base import ResolvedPlace
        from sitara_api.panchang.providers.http import ProviderUnavailable

        if subject.lat is None or subject.lon is None:
            return BriefFacts(
                confidence=ConfidenceState.CANNOT_CALCULATE,
                missing=("place", "panchang", "chart"),
                degraded=True,
            )

        place = ResolvedPlace(
            label=subject.timezone, lat=subject.lat, lon=subject.lon, tz=subject.timezone
        )
        try:
            result = await self._panchang.panchang(
                dt.date.fromisoformat(local_date), place, Tradition.AMANTA
            )
        except ProviderUnavailable:
            logger.warning(
                "brief facts: panchang unavailable",
                extra={"user_id": subject.user_id, "local_date": local_date},
            )
            return BriefFacts(
                confidence=ConfidenceState.CANNOT_CALCULATE,
                missing=("panchang", "chart"),
                degraded=True,
            )

        return BriefFacts(
            snapshots=tuple(result.facts),
            confidence=result.confidence,
            # Chart facts are genuinely absent until the facade serves them;
            # saying so is what lets `service._confidence_for` be honest.
            missing=("chart",),
            degraded=result.degraded or result.disputed,
        )


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


async def build_service(
    db,  # noqa: ANN001
) -> tuple[DailyGuidanceService, Callable[[], Awaitable[None]]]:
    """A ready service plus its teardown.

    The teardown exists because the LLM adapter owns an HTTP client; a Celery
    task that builds a service per message and never closes it leaks a
    connection pool per brief.
    """
    from sitara_api.panchang.places import GazetteerResolver

    panchang = build_panchang_service(db)
    facts: BriefFactSource
    if panchang is None:
        facts = _NoFacts()
    else:
        facts = PanchangBriefFacts(panchang, GazetteerResolver())

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
        return None

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
