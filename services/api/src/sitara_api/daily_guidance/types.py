"""Shared contracts for the §7.1 morning pipeline.

Every enum here is a closed set, and the closed set that matters most is not
declared here at all: the seventeen morning modules live in `sitara_schemas`
(§34.3) and this module imports them. A second copy is how an eighteenth
appears.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import StrEnum

from sitara_schemas.facts import ConfidenceState, FactSnapshot
from sitara_schemas.modules import MorningModule


class Density(StrEnum):
    """§28.2's three density modes.

    "Density changes ranking-engine output count, never facts." The default is
    the interest level captured at onboarding (S09), not a fixed value.
    """

    LOW = "low"  # skeptic-friendly: Tara's line + core card + practical strip
    MED = "med"  # default: + 2 contextual cards + panchang row
    HIGH = "high"  # devout: + timings, dasha context, extra observance cards


class Tier(StrEnum):
    """§7.1's priority queues: "paying users > trial > dormant".

    Three queues, and the ordering is the definition: a user is PAYING if they
    pay, else TRIAL if they are inside a trial, else DORMANT. DORMANT is the
    residual — post-trial free and lapsed accounts — and §7.1 gives it
    on-open generation only, "no waste". That reading is also what §28.2's
    Free variant already implies: a post-trial user without a payment sees
    generic panchang and locked personal cards, so there is no personalised
    brief to pre-generate for them anyway.
    """

    PAYING = "paying"
    TRIAL = "trial"
    DORMANT = "dormant"


#: Generation order for the wave. DORMANT is absent on purpose — it is not a
#: lower-priority queue, it is not enqueued at all.
GENERATED_TIERS: tuple[Tier, ...] = (Tier.PAYING, Tier.TRIAL)


class BriefStatus(StrEnum):
    """What a `daily_briefings` row actually contains.

    The three failure-shaped values are distinct because they degrade for
    different reasons and recover differently:

    * RANKING_ONLY is §7.1's COST LEVER — "if the morning queue depth breaches
      SLO, ranking-engine-only briefs (no LLM polish) ship first and upgrade
      lazily". Nothing is wrong; the brief is complete and unpolished, and a
      later pass may upgrade it.
    * VERIFIED_CORE_CARDS is §7.1's DEGRADE — "a failed brief degrades to
      'verified core cards' (panchang + one chart theme, no LLM) rather than
      nothing". Something failed. It does not upgrade itself.
    * FAILED is the row that could not even reach verified core cards, which
      means the facts were not there. §28.2's offline/degraded variants render
      the cached brief instead.
    """

    PENDING = "pending"
    POLISHED = "polished"
    RANKING_ONLY = "ranking_only"
    VERIFIED_CORE_CARDS = "verified_core_cards"
    FAILED = "failed"


#: Statuses §7.1's lazy upgrade may still improve.
UPGRADEABLE: frozenset[BriefStatus] = frozenset({BriefStatus.RANKING_ONLY})


class DegradeReason(StrEnum):
    """Why a brief is not what it should have been. Recorded, never inferred."""

    GROUNDING_FAILED = "grounding_failed"
    LLM_UNAVAILABLE = "llm_unavailable"
    PANCHANG_UNAVAILABLE = "panchang_unavailable"
    CHART_UNAVAILABLE = "chart_unavailable"
    LANGUAGE_QUALITY_FAILED = "language_quality_failed"


@dataclass(frozen=True)
class BriefSubject:
    """Who the wave is generating for, and everything needed to place them in
    local time. Assembled by the repository; the selector is pure over it."""

    user_id: str
    locale: str
    timezone: str
    #: "HH:MM" local, zero-padded (§23.5's brief-time picker; default 07:00).
    brief_time: str
    density: Density
    tier: Tier
    #: §30.2 Travel Mode: when False the user keeps home time and a location
    #: event does not move their brief.
    follow_timezone: bool = True
    #: Geo of the place their panchang is computed for — the shared cache row.
    lat: float | None = None
    lon: float | None = None


@dataclass(frozen=True)
class ComposedModule:
    """One of the seventeen, composed from facts and ready to render.

    `fact_ids` and `snapshots` are BOTH carried because §34.2 requires the full
    snapshot embedded at generation time, not a reference resolved later.
    """

    module: MorningModule
    #: Template-composed text — engine output, grounded by construction.
    text: str
    #: The polished rendering, when polish ran and passed grounding.
    polished_text: str | None = None
    snapshots: tuple[FactSnapshot, ...] = ()
    template_id: str = ""
    #: Set ONLY when the module was read back from `daily_briefings`.
    #:
    #: §6.4 stores `fact_ids` on the row and the full snapshots in
    #: `guidance_logs` (§34.2), so a brief re-read from the store has the ids
    #: and not the snapshots. Without this the ids vanished on read and a Trust
    #: Sheet opened on a stored brief would have had nothing to show — the
    #: citation surviving generation but not persistence.
    stored_fact_ids: tuple[str, ...] = ()

    @property
    def fact_ids(self) -> tuple[str, ...]:
        if self.snapshots:
            return tuple(snapshot.fact_id for snapshot in self.snapshots)
        return self.stored_fact_ids

    @property
    def rendered(self) -> str:
        """What the user reads. Falls back to the template, never to nothing."""
        return self.polished_text or self.text


@dataclass(frozen=True)
class Brief:
    """One `daily_briefings` row (§6.4), as the module sees it."""

    user_id: str
    #: The user's LOCAL calendar date (§32.13), ISO. Never a UTC date.
    local_date: str
    locale: str
    density: Density
    tier: Tier
    status: BriefStatus
    modules: tuple[ComposedModule, ...] = ()
    confidence: ConfidenceState | None = None
    idempotency_key: str = ""
    degrade_reason: DegradeReason | None = None
    generated_at: dt.datetime | None = None
    audio_ref: str | None = None
    opened_at: dt.datetime | None = None

    @property
    def fact_ids(self) -> tuple[str, ...]:
        seen: dict[str, None] = {}
        for module in self.modules:
            for fact_id in module.fact_ids:
                seen.setdefault(fact_id, None)
        return tuple(seen)

    @property
    def snapshots(self) -> tuple[FactSnapshot, ...]:
        by_id: dict[str, FactSnapshot] = {}
        for module in self.modules:
            for snapshot in module.snapshots:
                by_id.setdefault(snapshot.fact_id, snapshot)
        return tuple(by_id.values())

    @property
    def module_ids(self) -> tuple[MorningModule, ...]:
        return tuple(module.module for module in self.modules)


@dataclass(frozen=True)
class WaveMember:
    """A subject the tick selected, with the minute its generation starts.

    `due_at` is the exact local-time instant the notification is for; `start_at`
    is when generation should begin, spread across the lead window by the
    §7.1 hash so the IST-07:00 spike does not arrive as one thundering herd.
    """

    subject: BriefSubject
    local_date: str
    due_at: dt.datetime
    start_at: dt.datetime
    slot_minutes: int


@dataclass(frozen=True)
class WaveReport:
    """What one tick did. Returned so the caller can log it and the load
    simulation can histogram it without a database."""

    tick: dt.datetime
    selected: int = 0
    skipped_dormant: int = 0
    skipped_already_generated: int = 0
    by_slot: dict[int, int] = field(default_factory=dict)

    def summary(self) -> str:
        return (
            f"tick={self.tick.isoformat()} selected={self.selected} "
            f"dormant={self.skipped_dormant} already={self.skipped_already_generated}"
        )
