"""Fact adjudication — SPEC §32.2, with the §5.2 Layer D tolerances.

§32.2 replaced §5.2 Layer D's "served from the majority source" with an
authority rule. There is deliberately NO vote anywhere in this module:

  Chart class      Layer A authoritative, never voted. A vendor that disagrees
                   raises a REVIEW FLAG for the §12 comparison dashboard; the
                   served value and the user's confidence are untouched.

  Panchang class   DivineAPI primary (calendar interpretation, decision D1).
  Muhurat class    A DivineAPI↔Prokerala gap beyond tolerance still SERVES
  Festival class   DivineAPI, downgrades confidence to Approximate (§5.4's
                   "disputed fact in play"), and queues Jyotish adjudication.

Two unverified vendors can never overrule validated deterministic astronomy.

Pure functions only — no IO, no clock, no database. The nightly job in
compare_job.py supplies readings and persists whatever comes back.
"""

import datetime as dt
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from sitara_schemas.facts import ConfidenceState, FactSource

# §5.2 Layer D, verbatim: positions >1 arc-min, tithi/nakshatra boundary times
# >2 min, dasha dates >1 day.
POSITION_TOLERANCE_DEG = 1 / 60
BOUNDARY_TOLERANCE = dt.timedelta(minutes=2)
DASHA_TOLERANCE = dt.timedelta(days=1)


class FactClass(StrEnum):
    """Which authority rule applies (§32.2 + decision D1).

    CHART                — positions, lagna, dasha. Layer A authoritative, and
                           there is NO vendor substitute: §32.2 forbids
                           unverified vendors standing in for deterministic
                           astronomy, so without Layer A we decline (§5.3).

    PANCHANG_ASTRONOMY   — tithi/nakshatra/yoga boundary instants and
                           sunrise/sunset. A hybrid, and deliberately so:
                           these ARE deterministic astronomy, so Layer A is
                           authoritative and is never voted (D1) — but they are
                           also panchang facts served through the §8 ladder,
                           so when our engine cannot answer, §32.2's plain rule
                           takes over: DivineAPI serves, and a Prokerala
                           disagreement beyond tolerance disputes and queues.

    PANCHANG / MUHURAT / FESTIVAL
                         — calendar interpretation. DivineAPI primary always.
    """

    CHART = "chart"
    PANCHANG_ASTRONOMY = "panchang_astronomy"
    PANCHANG = "panchang"
    MUHURAT = "muhurat"
    FESTIVAL = "festival"


_VENDOR_PRIMARY_CLASSES = frozenset({FactClass.PANCHANG, FactClass.MUHURAT, FactClass.FESTIVAL})


@dataclass(frozen=True)
class Reading:
    """One source's answer for one fact."""

    source: FactSource
    instant: dt.datetime


@dataclass(frozen=True)
class AdjudicationRecord:
    """Queued for the Jyotish lead (§32.2) and shown on the §12 dashboard.

    Both readings are embedded rather than referenced: a vendor's answer can
    change under us, and a reviewer must see what we actually served against
    what we actually got (§34.2's snapshot principle).
    """

    fact_class: FactClass
    fact_key: str
    served_source: FactSource
    delta_seconds: float
    tolerance_seconds: float
    readings: dict[str, str]
    status: str = "pending"
    kind: str = "vendor_disagreement"

    def to_document(self) -> dict[str, Any]:
        return {
            "fact_class": self.fact_class.value,
            "fact_key": self.fact_key,
            "served_source": self.served_source.value,
            "delta_seconds": self.delta_seconds,
            "tolerance_seconds": self.tolerance_seconds,
            "readings": self.readings,
            "status": self.status,
            "kind": self.kind,
        }


@dataclass(frozen=True)
class Adjudication:
    """The outcome: what to serve, how confident to sound, what to escalate."""

    source: FactSource | None
    served: dt.datetime | None
    disputed: bool = False
    review_flagged: bool = False
    confidence: ConfidenceState | None = None
    cacheable: bool = False
    adjudication: AdjudicationRecord | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)


def _gap(a: Reading | None, b: Reading | None) -> dt.timedelta | None:
    if a is None or b is None:
        return None
    return abs(a.instant - b.instant)


def _beyond(gap: dt.timedelta | None, tolerance: dt.timedelta) -> bool:
    """'Beyond tolerance' is strictly greater — a gap exactly at the limit is
    still agreement, so a fact does not flip state on a rounding artefact."""
    return gap is not None and gap > tolerance


def _adjudicate_chart(
    layer_a: Reading | None,
    divineapi: Reading | None,
    prokerala: Reading | None,
    tolerance: dt.timedelta,
) -> Adjudication:
    if layer_a is None:
        # Our engine could not answer. A chart fact has no vendor substitute:
        # §32.2 forbids unverified vendors standing in for deterministic
        # astronomy, so we decline rather than serve one (§5.3).
        return Adjudication(
            source=None,
            served=None,
            confidence=ConfidenceState.CANNOT_CALCULATE,
            notes=("layer_a_unavailable",),
        )

    flagged = _beyond(_gap(layer_a, divineapi), tolerance) or _beyond(
        _gap(layer_a, prokerala), tolerance
    )
    return Adjudication(
        source=FactSource.LAYER_A,
        served=layer_a.instant,
        disputed=False,  # a chart fact is never disputed — it is authoritative
        review_flagged=bool(flagged),
        confidence=None,  # nothing to downgrade; the caller keeps its own state
        cacheable=True,
        notes=("vendor_disagreement_flagged",) if flagged else (),
    )


def _adjudicate_vendor_primary(
    fact_class: FactClass,
    fact_key: str,
    layer_a: Reading | None,
    divineapi: Reading | None,
    prokerala: Reading | None,
    tolerance: dt.timedelta,
) -> Adjudication:
    # A large gap against our own engine is worth an admin's attention even
    # where our engine is not the authority.
    engine_flag = _beyond(_gap(layer_a, divineapi), tolerance)

    if divineapi is not None:
        gap = _gap(divineapi, prokerala)
        if _beyond(gap, tolerance):
            assert gap is not None and prokerala is not None
            record = AdjudicationRecord(
                fact_class=fact_class,
                fact_key=fact_key,
                served_source=FactSource.DIVINEAPI,
                delta_seconds=gap.total_seconds(),
                tolerance_seconds=tolerance.total_seconds(),
                readings={
                    r.source.value: r.instant.isoformat()
                    for r in (layer_a, divineapi, prokerala)
                    if r is not None
                },
            )
            return Adjudication(
                source=FactSource.DIVINEAPI,
                served=divineapi.instant,
                disputed=True,
                review_flagged=True,
                # §5.4: "time window given; OR disputed fact in play".
                confidence=ConfidenceState.APPROXIMATE,
                cacheable=True,
                adjudication=record,
                notes=("vendor_disagreement_disputed",),
            )
        return Adjudication(
            source=FactSource.DIVINEAPI,
            served=divineapi.instant,
            review_flagged=bool(engine_flag),
            cacheable=True,
            notes=("engine_disagreement_flagged",) if engine_flag else (),
        )

    # ---- §8 degradation ladder, in order.
    if layer_a is not None:
        # "DivineAPI down → internal panchang (if within validated scope)".
        return Adjudication(
            source=FactSource.LAYER_A,
            served=layer_a.instant,
            confidence=ConfidenceState.TRADITION_BASED_GENERAL,
            cacheable=False,  # not the system of record for calendar facts
            notes=("degraded_to_layer_a",),
        )

    if prokerala is not None:
        # "…or Prokerala". Its ToS forbids it being the system of record, so
        # this answer is ephemeral and explicitly degraded.
        return Adjudication(
            source=FactSource.PROKERALA,
            served=prokerala.instant,
            confidence=ConfidenceState.APPROXIMATE,
            cacheable=False,
            notes=("degraded_to_prokerala", "never_cached_tos"),
        )

    return Adjudication(
        source=None,
        served=None,
        confidence=ConfidenceState.CANNOT_CALCULATE,
        notes=("no_source_available",),
    )


def adjudicate(
    fact_class: FactClass,
    *,
    layer_a: Reading | None,
    divineapi: Reading | None,
    prokerala: Reading | None,
    fact_key: str = "",
    tolerance: dt.timedelta = BOUNDARY_TOLERANCE,
) -> Adjudication:
    """Apply §32.2's authority rules to one fact's readings.

    `tolerance` defaults to the boundary-time limit; pass DASHA_TOLERANCE for
    dasha dates. Position comparisons are angular and use
    POSITION_TOLERANCE_DEG through compare_positions().
    """
    if fact_class is FactClass.CHART:
        return _adjudicate_chart(layer_a, divineapi, prokerala, tolerance)
    if fact_class is FactClass.PANCHANG_ASTRONOMY:
        # Layer A wins whenever it has an answer; otherwise the vendors are all
        # we have and §32.2's DivineAPI-primary rule governs them.
        if layer_a is not None:
            return _adjudicate_chart(layer_a, divineapi, prokerala, tolerance)
        return _adjudicate_vendor_primary(
            fact_class, fact_key, None, divineapi, prokerala, tolerance
        )
    if fact_class in _VENDOR_PRIMARY_CLASSES:
        return _adjudicate_vendor_primary(
            fact_class, fact_key, layer_a, divineapi, prokerala, tolerance
        )
    raise ValueError(f"unhandled fact class: {fact_class}")  # pragma: no cover


def positions_disagree(a_deg: float, b_deg: float) -> bool:
    """Angular comparison for §5.2 Layer D's 1-arc-min position tolerance,
    wrapping correctly across 0°/360°."""
    delta = abs(a_deg - b_deg) % 360.0
    return min(delta, 360.0 - delta) > POSITION_TOLERANCE_DEG
