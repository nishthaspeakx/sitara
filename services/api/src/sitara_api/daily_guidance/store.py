"""The `daily_briefings` and `guidance_logs` writes (§6.4, §34.2, §32.13).

Two collections, written together, for one reason: §34.2 requires every
artefact that cites a fact to embed the fact's full snapshot AT GENERATION
TIME. The brief carries the fact-IDs a card renders from; `guidance_logs`
carries the snapshots those IDs meant this morning. A Trust Sheet opened in
eight months reads the snapshot, never a recomputation — which is why the
recomputation is not offered here at all.

The idempotent write is the other half. §32.13 binds one brief per user-local
date, and the unique index on (user_id, date) is what actually enforces it —
not the pre-check in the wave selector, which two workers can pass at the same
instant. `upsert` is written so that losing that race is a normal outcome with
a defined result rather than an exception nobody handles.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from sitara_schemas.facts import ConfidenceState
from sitara_schemas.modules import MorningModule

from sitara_api.chat_orchestration.store import to_object_id
from sitara_api.daily_guidance.idempotency import briefing_key, is_stale
from sitara_api.daily_guidance.types import (
    Brief,
    BriefStatus,
    ComposedModule,
    DegradeReason,
    Density,
    Tier,
)
from sitara_api.db.documents import stamp

logger = logging.getLogger(__name__)


def _module_doc(module: ComposedModule) -> dict[str, Any]:
    """One embedded module. §6.4 keeps `modules[]` "embedded, bounded"."""
    return {
        "module": module.module.value,
        "text": module.rendered,
        "template_id": module.template_id,
        "fact_ids": list(module.fact_ids),
        "polished": module.polished_text is not None,
    }


def _module_from_doc(doc: dict[str, Any]) -> ComposedModule:
    return ComposedModule(
        module=MorningModule(doc["module"]),
        text=doc.get("text") or "",
        polished_text=doc.get("text") if doc.get("polished") else None,
        template_id=doc.get("template_id") or "",
    )


class BriefStore:
    def __init__(self, db) -> None:  # noqa: ANN001
        self._db = db

    async def get(self, user_id: str, local_date: str) -> Brief | None:
        doc = await self._db.daily_briefings.find_one(
            {"user_id": to_object_id(user_id, field_name="daily_briefings.user_id"),
             "date": local_date}
        )
        return self._from_doc(doc) if doc else None

    async def upsert(self, brief: Brief, *, now: dt.datetime | None = None) -> Brief:
        """Write the brief under §32.13's key. Last writer for a local date wins.

        "Wins" is correct rather than merely convenient: the writers competing
        for one (user, date) are the scheduled wave, an on-open generation and a
        targeted regenerate, and in every pairing the later one has strictly
        fresher inputs — a new locale, a new city, or facts the earlier one
        could not reach.
        """
        moment = now or dt.datetime.now(dt.UTC)
        key = briefing_key(brief.user_id, brief.local_date, brief.locale)
        document = stamp(
            {
                "user_id": to_object_id(
                    brief.user_id, field_name="daily_briefings.user_id"
                ),
                "date": brief.local_date,
                "locale": brief.locale,
                "modules": [_module_doc(m) for m in brief.modules],
                "fact_ids": list(brief.fact_ids),
                "confidence": brief.confidence.value if brief.confidence else None,
                "audio_ref": brief.audio_ref,
                "opened_at": brief.opened_at,
                "status": brief.status.value,
                "idempotency_key": key,
                "density": brief.density.value,
                "tier": brief.tier.value,
                "generated_at": brief.generated_at or moment,
                "degrade_reason": (
                    brief.degrade_reason.value if brief.degrade_reason else None
                ),
            },
            now=moment,
        )
        # `created_at` must not be reset when a regenerate replaces a row, so it
        # is excluded from $set and applied only on insert.
        created_at = document.pop("created_at")
        await self._db.daily_briefings.update_one(
            {"user_id": document["user_id"], "date": brief.local_date},
            {"$set": document, "$setOnInsert": {"created_at": created_at}},
            upsert=True,
        )
        return Brief(**{**brief.__dict__, "idempotency_key": key, "generated_at": moment})

    async def write_guidance_log(self, brief: Brief, *, now: dt.datetime | None = None) -> None:
        """§34.2: the why-payload with FULL snapshots embedded.

        Written even for a degraded brief. "Why did Tara say so little on the
        14th?" is a question the audit trail has to be able to answer, and a
        log written only on the happy path answers it for every morning except
        the ones anyone would ask about.
        """
        moment = now or dt.datetime.now(dt.UTC)
        document = stamp(
            {
                "user_id": to_object_id(brief.user_id, field_name="guidance_logs.user_id"),
                "date": brief.local_date,
                "briefing_id": None,
                "message_id": None,
                "fact_ids": list(brief.fact_ids),
                "fact_snapshots": [s.model_dump(mode="json") for s in brief.snapshots],
                "template_ids": [m.template_id for m in brief.modules],
                "confidence": (
                    brief.confidence.value
                    if brief.confidence
                    else ConfidenceState.CANNOT_CALCULATE.value
                ),
                "why": {
                    "source": "daily_brief",
                    "status": brief.status.value,
                    "density": brief.density.value,
                    "tier": brief.tier.value,
                    "modules": [m.module.value for m in brief.modules],
                    "degrade_reason": (
                        brief.degrade_reason.value if brief.degrade_reason else None
                    ),
                },
            },
            now=moment,
        )
        await self._db.guidance_logs.insert_one(document)

    async def mark_opened(self, user_id: str, local_date: str, when: dt.datetime) -> bool:
        """§23.8 / §7.1's TTS gate reads the trailing open rate off this."""
        result = await self._db.daily_briefings.update_one(
            {
                "user_id": to_object_id(user_id, field_name="daily_briefings.user_id"),
                "date": local_date,
                "opened_at": None,
            },
            {"$set": {"opened_at": when, "updated_at": when}},
        )
        return result.modified_count == 1

    async def generated_pairs(self, local_dates: set[str]) -> frozenset[tuple[str, str]]:
        """(user_id, local_date) already bound — the wave's cheap pre-filter.

        Cheap and advisory. The unique index is the guarantee; this only keeps
        the queue from carrying work that will be discarded on arrival.
        """
        cursor = self._db.daily_briefings.find(
            {"date": {"$in": list(local_dates)}}, {"user_id": 1, "date": 1}
        )
        return frozenset([(str(doc["user_id"]), doc["date"]) async for doc in cursor])

    async def stale_for_locale(self, user_id: str, local_date: str, locale: str) -> bool:
        """§32.7: is the stored brief bound under a different key?"""
        doc = await self._db.daily_briefings.find_one(
            {
                "user_id": to_object_id(user_id, field_name="daily_briefings.user_id"),
                "date": local_date,
            },
            {"idempotency_key": 1},
        )
        if doc is None:
            return False
        return is_stale(
            doc.get("idempotency_key", ""), briefing_key(user_id, local_date, locale)
        )

    def _from_doc(self, doc: dict[str, Any]) -> Brief:
        degrade = doc.get("degrade_reason")
        confidence = doc.get("confidence")
        return Brief(
            user_id=str(doc["user_id"]),
            local_date=doc["date"],
            locale=doc["locale"],
            density=Density(doc.get("density", Density.MED.value)),
            tier=Tier(doc.get("tier", Tier.PAYING.value)),
            status=BriefStatus(doc["status"]),
            modules=tuple(_module_from_doc(m) for m in doc.get("modules", ())),
            confidence=ConfidenceState(confidence) if confidence else None,
            idempotency_key=doc.get("idempotency_key", ""),
            degrade_reason=DegradeReason(degrade) if degrade else None,
            generated_at=doc.get("generated_at"),
            audio_ref=doc.get("audio_ref"),
            opened_at=doc.get("opened_at"),
        )
