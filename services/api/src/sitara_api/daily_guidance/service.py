"""§7.1's pipeline, assembled (diagram 5).

    fetch chart facts (cached) → panchang facts (shared cache) → ranking engine
    picks from the 17 modules → template composition + LLM polish → grounding
    validation → TTS pre-render (gated) → store `daily_briefings` →
    notification enqueued for exact local time

Each of those is its own module in this package; this one is the sequence, the
degradation ladder and the two places §7.1 gives the pipeline a choice.

**The cost lever.** "if the morning queue depth breaches SLO, ranking-engine-
only briefs (no LLM polish) ship first and upgrade lazily". Passing
`skip_polish=True` produces exactly that: a complete, verified, unpolished
brief marked RANKING_ONLY, which a later pass may upgrade. It is not a
degraded brief and is not recorded as one.

**The degrade.** "a failed brief degrades to 'verified core cards' (panchang +
one chart theme, no LLM) rather than nothing". Two things trigger it: facts too
thin to compose a real brief, and a polish pass in which EVERY line failed
grounding after its one corrective regeneration (diagram 5's `fail` edge). A
provider outage is neither — §8 degrades that gracefully, the composed text is
already verified, and the brief ships as RANKING_ONLY.

**The TTS gate.** "TTS pre-render (only for users with voice-brief enabled and
open-rate >20% trailing — cost control; others synthesize on first open)".
Declared here and delegated to the voice module, which does not exist yet; the
decision is made and recorded so that adding the renderer changes no logic here
(the same discipline §37 records for §9's TTS stage).
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Sequence
from dataclasses import dataclass

from sitara_schemas.facts import ConfidenceState, FactKind, FactSnapshot
from sitara_schemas.modules import MorningModule

from sitara_api.daily_guidance import notify, ranking
from sitara_api.daily_guidance.idempotency import briefing_key
from sitara_api.daily_guidance.polish import BriefPolisher, PolishReport
from sitara_api.daily_guidance.store import BriefStore
from sitara_api.daily_guidance.templates import BriefComposer
from sitara_api.daily_guidance.types import (
    Brief,
    BriefStatus,
    BriefSubject,
    ComposedModule,
    DegradeReason,
    WaveMember,
)

logger = logging.getLogger(__name__)

#: §7.1's TTS gate: "open-rate >20% trailing".
TTS_OPEN_RATE_THRESHOLD = 0.20


@dataclass(frozen=True)
class BriefFacts:
    """What the fact stage produced, and what it could not.

    `missing` is carried rather than inferred so the degrade path can say WHY
    in `degrade_reason` — "the panchang cell was cold" and "this user has no
    birth time" produce the same short brief and are not the same problem.
    """

    snapshots: tuple[FactSnapshot, ...] = ()
    confidence: ConfidenceState = ConfidenceState.VERIFIED
    missing: tuple[str, ...] = ()
    degraded: bool = False


class BriefFactSource:
    """What `generate` needs from the astrology facade.

    A Protocol in all but name, kept as a class so the composite implementation
    below has somewhere to live. Implementations MUST NOT raise on a partial
    result: §7.1's degrade needs whatever facts exist, and an exception here
    would turn a thin brief into no brief.
    """

    async def fetch(
        self, subject: BriefSubject, local_date: str
    ) -> BriefFacts:  # pragma: no cover - interface
        raise NotImplementedError


@dataclass(frozen=True)
class GenerationResult:
    brief: Brief
    notification: notify.BriefNotification | None
    polish: PolishReport


@dataclass(frozen=True)
class ComposedBrief:
    """The ladder's verdict, before anything is persisted or notified.

    Split out of `generate_for` so the four outcomes can be reached without a
    store, a queue or a clock. Two callers need exactly that: the tests, which
    should be able to assert "these facts degrade to core cards" without a
    database; and §28.2's dev variant switcher, which renders every variant from
    real engine output and would otherwise have needed a fake `BriefStore` —
    and a fake that accepts what the real one rejects is a defect in the fake,
    so the better answer was not to need one.
    """

    modules: tuple[ComposedModule, ...]
    status: BriefStatus
    degrade_reason: DegradeReason | None
    polish: PolishReport


def _relevance_for(facts: BriefFacts) -> dict[MorningModule, float]:
    """This morning's nudges to the contextual ranking.

    `RankingContext.relevance` exists for exactly this — "a festival today, a
    family birthday tomorrow" — and the festival is the case that has to use it,
    because §28.2 puts a festival on TWO surfaces: the banner above the core
    card (§32.1's only permitted one) and a contextual card among the max four.

    Left unnudged, `festival_observance` sits mid-pool and loses the MED-density
    cut to `family_reminder` and `priorities`, so a festival morning renders no
    festival anywhere — the day's most visible fact, invisible. The nudge is a
    ranking preference, not a bypass: the module is still gated on having a
    `FESTIVAL_OBSERVANCE` fact like everything else (§5.3).
    """
    has_festival = any(
        snapshot.kind is FactKind.FESTIVAL_OBSERVANCE for snapshot in facts.snapshots
    )
    return {MorningModule.FESTIVAL_OBSERVANCE: 10.0} if has_festival else {}


async def compose_brief(
    facts: BriefFacts,
    subject: BriefSubject,
    *,
    polisher: BriefPolisher | None = None,
    skip_polish: bool = False,
    inputs: dict[str, str] | None = None,
) -> ComposedBrief:
    """§7.1's ranking → composition → polish → degradation ladder.

    Every branch here is a spec line, and the three failure-shaped outcomes are
    NOT interchangeable — see `BriefStatus`. In particular a provider outage
    lands on RANKING_ONLY, not VERIFIED_CORE_CARDS: the composed text is already
    verified, so §8 degrades it gracefully rather than treating it as a
    grounding failure.
    """
    context = ranking.RankingContext(
        density=subject.density,
        available_inputs=frozenset(inputs or ()),
        relevance=_relevance_for(facts),
    )
    ranked = ranking.rank(facts.snapshots, context)
    composer = BriefComposer(inputs=inputs)
    modules = composer.compose_all(ranked, subject.locale)

    status = BriefStatus.POLISHED
    degrade_reason: DegradeReason | None = None
    report = PolishReport()

    if not modules:
        # Nothing composed at all. Fall to core cards; if those are empty too,
        # the facts were not there and the brief FAILS honestly rather than
        # shipping an empty card set.
        modules = composer.compose_all(ranking.core_cards(facts.snapshots), subject.locale)
        status = BriefStatus.VERIFIED_CORE_CARDS if modules else BriefStatus.FAILED
        degrade_reason = (
            DegradeReason.PANCHANG_UNAVAILABLE
            if "panchang" in facts.missing
            else DegradeReason.CHART_UNAVAILABLE
        )
    elif skip_polish or polisher is None:
        # §7.1's cost lever. Complete and verified; simply not polished.
        status = BriefStatus.RANKING_ONLY
    else:
        modules, report = await polisher.polish(modules, subject.locale, subject.density)
        if report.unavailable:
            status = BriefStatus.RANKING_ONLY
        elif report.all_rejected:
            # Diagram 5's `fail` edge off grounding validation.
            core = composer.compose_all(ranking.core_cards(facts.snapshots), subject.locale)
            modules = core or modules
            status = BriefStatus.VERIFIED_CORE_CARDS
            degrade_reason = DegradeReason.GROUNDING_FAILED

    return ComposedBrief(
        modules=tuple(modules),
        status=status,
        degrade_reason=degrade_reason,
        polish=report,
    )


class DailyGuidanceService:
    def __init__(
        self,
        *,
        facts: BriefFactSource,
        store: BriefStore,
        queue: notify.NotificationQueue | None = None,
        polisher: BriefPolisher | None = None,
    ) -> None:
        self._facts = facts
        self._store = store
        self._queue = queue
        self._polisher = polisher

    # -- the wave ----------------------------------------------------------

    async def generate_for(
        self,
        member: WaveMember,
        *,
        skip_polish: bool = False,
        inputs: dict[str, str] | None = None,
        now: dt.datetime | None = None,
    ) -> GenerationResult:
        """One brief, end to end (diagram 5)."""
        moment = now or dt.datetime.now(dt.UTC)
        subject = member.subject
        facts = await self._facts.fetch(subject, member.local_date)

        composed = await compose_brief(
            facts,
            subject,
            polisher=self._polisher,
            skip_polish=skip_polish,
            inputs=inputs,
        )
        modules = composed.modules
        status = composed.status
        degrade_reason = composed.degrade_reason
        report = composed.polish

        brief = Brief(
            user_id=subject.user_id,
            local_date=member.local_date,
            locale=subject.locale,
            density=subject.density,
            tier=subject.tier,
            status=status,
            modules=tuple(modules),
            confidence=_confidence_for(status, facts),
            idempotency_key=briefing_key(
                subject.user_id, member.local_date, subject.locale
            ),
            degrade_reason=degrade_reason,
            generated_at=moment,
        )

        stored = await self._store.upsert(brief, now=moment)
        await self._store.write_guidance_log(stored, now=moment)

        notification = None
        if self._queue is not None:
            notification = notify.build(
                stored, timezone=subject.timezone, due_at=member.due_at
            )
            if notification is not None:
                await self._queue.enqueue(notification)

        logger.info(
            "brief generated",
            extra={
                "user_id": subject.user_id,
                "local_date": member.local_date,
                "status": status.value,
                "modules": len(modules),
                "polish": report.accepted,
            },
        )
        return GenerationResult(brief=stored, notification=notification, polish=report)

    async def generate_on_open(
        self,
        subject: BriefSubject,
        local_date: str,
        *,
        due_at: dt.datetime,
        inputs: dict[str, str] | None = None,
        now: dt.datetime | None = None,
    ) -> GenerationResult:
        """§7.1's path for dormant users, and §32.13's for a missed local date.

        "dormant users get on-open generation only — no waste" and "a missed
        local date generates on open" are the same code path: the app asked for
        a brief that does not exist yet, so make it now. The notification is
        still enqueued — it will be expired or superseded by §23.4's rules if
        the moment for it has passed, which is the correct place for that
        decision rather than here.
        """
        member = WaveMember(
            subject=subject,
            local_date=local_date,
            due_at=due_at,
            start_at=now or dt.datetime.now(dt.UTC),
            slot_minutes=0,
        )
        return await self.generate_for(member, inputs=inputs, now=now)

    # -- §7.1's TTS gate ---------------------------------------------------

    @staticmethod
    def should_pre_render_tts(*, voice_brief_enabled: bool, trailing_open_rate: float) -> bool:
        """"only for users with voice-brief enabled and open-rate >20% trailing
        — cost control; others synthesize on first open"."""
        return voice_brief_enabled and trailing_open_rate > TTS_OPEN_RATE_THRESHOLD


def _confidence_for(status: BriefStatus, facts: BriefFacts) -> ConfidenceState:
    """§5.4's state for the brief as a whole.

    A degraded brief is TRADITION_BASED_GENERAL, not APPROXIMATE: verified core
    cards are panchang facts, which are true — what is missing is the personal
    reading, and §5.4's tradition-based state is exactly "we can tell you what
    the day holds generally, not what it holds for you".
    """
    if status is BriefStatus.FAILED:
        return ConfidenceState.CANNOT_CALCULATE
    if status is BriefStatus.VERIFIED_CORE_CARDS:
        return ConfidenceState.TRADITION_BASED_GENERAL
    if facts.degraded:
        return ConfidenceState.APPROXIMATE
    return facts.confidence


async def run_wave(
    service: DailyGuidanceService,
    members: Sequence[WaveMember],
    *,
    skip_polish: bool = False,
    now: dt.datetime | None = None,
) -> list[GenerationResult]:
    """Generate a tick's wave in order.

    Sequential on purpose. §9's prompt cache rewards a shared stable prefix and
    the wave's members share one per locale; running them back to back keeps
    that prefix hot, which is the mechanism §7.1 relies on to make the Claude
    call "the only per-user marginal cost". Concurrency belongs at the Celery
    worker level, where it is bounded by the queue's own concurrency budget
    rather than by how many members one tick happened to select.
    """
    results: list[GenerationResult] = []
    for member in members:
        try:
            results.append(
                await service.generate_for(member, skip_polish=skip_polish, now=now)
            )
        except Exception:  # noqa: BLE001
            # §7.1: "Retries: 3× exponential" is the task's business, not the
            # loop's. One member's failure must not cost the rest of the wave
            # their morning.
            logger.exception(
                "brief generation failed",
                extra={
                    "user_id": member.subject.user_id,
                    "local_date": member.local_date,
                },
            )
    return results
