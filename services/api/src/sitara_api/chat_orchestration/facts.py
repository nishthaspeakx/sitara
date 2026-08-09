"""Stages 6 and 7 — fact tool-calls and fact validation (§5.3, §9).

§9: "facts via tool calls to astrology/numerology services — the LLM requests
facts, never computes them." The request came from the router (stage 3) and was
already filtered through the §22.8 allowlist; this module executes it against
the astrology facade and then validates what came back.

Two rules give this module its shape:

* A tool we cannot serve is DECLINED, never approximated. The pipeline turns a
  decline into an honest "I can't calculate this" rather than handing the model
  an empty payload to be creative with (§5.3). The chart tools carry THREE
  distinct declines and the pipeline renders them differently: no facade wired,
  birth data too thin (Tara asks — §28.2's missing-birth-time variant), and the
  engine down (Tara degrades — §8).
* Only validated snapshots reach interpretation (§5.3 step 7). A stale transit
  is as wrong as an invented one, so `validate` checks the clock too.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from zoneinfo import ZoneInfo

from sitara_schemas.facts import ConfidenceState, FactKind, FactSnapshot, Tradition

from sitara_api.chat_orchestration.types import BirthProfile, FactTool, ValidatedFacts

logger = logging.getLogger(__name__)


class FactToolUnavailable(Exception):
    """This tool cannot answer right now — decline, do not approximate."""

    def __init__(self, tool: FactTool, reason: str) -> None:
        self.tool = tool
        self.reason = reason
        super().__init__(f"{tool.value}: {reason}")


@dataclass(frozen=True)
class FactContext:
    """Everything a tool call needs except which tool it is."""

    user_id: str
    now: dt.datetime
    locale: str
    profile: BirthProfile
    place_label: str | None = None
    slots: dict[str, str] | None = None


@dataclass(frozen=True)
class FactQuery:
    tool: FactTool
    user_id: str
    now: dt.datetime
    locale: str
    profile: BirthProfile
    place_label: str | None = None
    slots: dict[str, str] | None = None

    @classmethod
    def of(cls, tool: FactTool, context: FactContext) -> FactQuery:
        return cls(
            tool=tool,
            user_id=context.user_id,
            now=context.now,
            locale=context.locale,
            profile=context.profile,
            place_label=context.place_label,
            slots=context.slots,
        )


class FactProvider(Protocol):
    async def fetch(self, query: FactQuery) -> Sequence[FactSnapshot]: ...


# --------------------------------------------------------------------------
# Fetch
# --------------------------------------------------------------------------


async def gather_facts(
    tools: Sequence[FactTool],
    provider: FactProvider,
    context: FactContext,
) -> tuple[list[FactSnapshot], list[str]]:
    """Run the granted tools concurrently. Returns (snapshots, declines).

    One tool failing does not fail the turn: the others still answer and the
    §8 ladder decides what the reduced payload is worth. What it must not do
    is disappear — every decline is returned so the reply can say so.
    """
    if not tools:
        return [], []

    async def run(tool: FactTool) -> tuple[FactTool, list[FactSnapshot] | str]:
        try:
            return tool, list(await provider.fetch(FactQuery.of(tool, context)))
        except FactToolUnavailable as exc:
            return tool, exc.reason
        except Exception:  # noqa: BLE001 — an adapter fault is a decline, not a 500
            logger.warning("fact tool %s failed", tool.value, exc_info=False)
            return tool, "tool_error"

    snapshots: list[FactSnapshot] = []
    declines: list[str] = []
    for tool, outcome in await asyncio.gather(*(run(tool) for tool in tools)):
        if isinstance(outcome, str):
            declines.append(f"{tool.value}:{outcome}")
        else:
            snapshots.extend(outcome)
    return snapshots, declines


# --------------------------------------------------------------------------
# Validate (§5.3 step 6)
# --------------------------------------------------------------------------

#: Kinds whose value is only true inside a window. A natal fact has no
#: expiry (it dies by chart_version bump, §34.2), so it is not checked here.
_TIME_BOUNDED: frozenset[FactKind] = frozenset(
    {
        FactKind.TRANSIT_GRAHA_POSITION,
        FactKind.TRANSIT_GRAHA_HOUSE,
        FactKind.PANCHANG_TITHI_BOUNDARY,
        FactKind.PANCHANG_NAKSHATRA_BOUNDARY,
        FactKind.PANCHANG_DAY_TIMING,
        FactKind.MUHURAT_WINDOW,
    }
)

#: A muhurat window is deliberately in the future — it is a recommendation,
#: not a description of now — so it is exempt from the staleness check.
_FUTURE_DATED: frozenset[FactKind] = frozenset({FactKind.MUHURAT_WINDOW})


def validate(
    snapshots: Sequence[FactSnapshot],
    now: dt.datetime,
    *,
    disputed: bool = False,
    notes: Sequence[str] = (),
) -> ValidatedFacts:
    """Schema, ranges, clock and duplicates. Only survivors are interpretable."""
    accepted: list[FactSnapshot] = []
    rejected: list[str] = []
    seen: set[str] = set()

    for snapshot in snapshots:
        try:
            # Re-validate rather than trust the object: the ranges and the
            # kind↔value_kind pairing live in the model, and a provider that
            # hand-built a snapshot must not get to skip them.
            checked = FactSnapshot.model_validate(snapshot.model_dump())
        except Exception:  # noqa: BLE001
            rejected.append(f"{getattr(snapshot, 'fact_id', '?')}:schema")
            continue

        if checked.fact_id in seen:
            rejected.append(f"{checked.fact_id}:duplicate")
            continue
        if checked.confidence is ConfidenceState.CANNOT_CALCULATE:
            rejected.append(f"{checked.fact_id}:not_calculable")
            continue
        if _is_stale(checked, now):
            rejected.append(f"{checked.fact_id}:stale")
            continue

        seen.add(checked.fact_id)
        accepted.append(checked)

    return ValidatedFacts(
        snapshots=tuple(accepted),
        rejected=tuple(rejected),
        disputed=disputed,
        notes=tuple(notes),
    )


def _is_stale(snapshot: FactSnapshot, now: dt.datetime) -> bool:
    if snapshot.kind not in _TIME_BOUNDED or snapshot.kind in _FUTURE_DATED:
        return False
    return snapshot.valid_to is not None and snapshot.valid_to < now


# --------------------------------------------------------------------------
# The astrology-facade provider
# --------------------------------------------------------------------------


class AstrologyFacadeProvider:
    """Fact tools over the existing M3/M4 facade.

    §13: birth details are reachable "only via the astrology facade (no generic
    query path)". This class is a caller of that facade, not a second door to
    the data — it holds no birth details of its own.
    """

    def __init__(
        self,
        *,
        panchang_service: object | None,
        numerology_adapter: object | None,
        place_resolver: object | None,
        astrology_facade: object | None = None,
        default_place: str = "Delhi",
        tradition: Tradition = Tradition.AMANTA,
    ) -> None:
        self._panchang = panchang_service
        self._numerology = numerology_adapter
        self._places = place_resolver
        # §13's single door to birth details. None means the chart tools
        # decline, which is what M5 did unconditionally.
        self._astrology = astrology_facade
        self._default_place = default_place
        self._tradition = tradition

    async def fetch(self, query: FactQuery) -> Sequence[FactSnapshot]:
        match query.tool:
            case FactTool.PANCHANG_DAY:
                return await self._panchang_day(query)
            case FactTool.PANCHANG_DAY_TIMINGS:
                return await self._day_timings(query)
            case FactTool.MUHURAT_WINDOW:
                return await self._muhurat(query)
            case FactTool.NUMEROLOGY_PROFILE:
                return await self._numerology_profile(query)
            case FactTool.NATAL_CHART:
                return await self._chart(query, include_transits=False)
            case FactTool.TRANSITS:
                return await self._chart(query, include_transits=True)
        raise FactToolUnavailable(query.tool, "unknown_tool")

    # -- chart (§5.2 Layer A, through the §13 facade) ----------------------

    async def _chart(
        self, query: FactQuery, *, include_transits: bool
    ) -> Sequence[FactSnapshot]:
        """Natal, dasha and (for TRANSITS) today's gochar.

        Three declines, kept apart because the pipeline renders them
        differently: no facade wired at all, birth data too thin to compute
        (§5.3 — Tara ASKS, per §28.2's missing-birth-time variant), and the
        engine being down (§8 — Tara degrades). Collapsing them would either
        nag a user about an outage or hide a real gap behind a retry.
        """
        from sitara_api.astrology.chart_adapter import (
            ChartEngineUnavailable,
            InsufficientBirthData,
        )

        if self._astrology is None:
            raise FactToolUnavailable(query.tool, "chart_facade_unavailable")

        # §5.3 forbids guessing. Defaulting to UTC here looked harmless and
        # shifts the LOCAL DATE by up to a day — which is the date the transits
        # are computed for, so a user with no zone on file would have been
        # served yesterday's sky with today's confidence.
        zone = query.profile.tz
        if not zone:
            raise FactToolUnavailable(query.tool, "no_timezone_on_profile")
        local_date = query.now.astimezone(ZoneInfo(zone)).date().isoformat()
        try:
            bundle = await self._astrology.chart_for(  # type: ignore[attr-defined]
                query.user_id,
                local_date=local_date,
                timezone=zone,
                chart_version=query.profile.chart_version,
                include_transits=include_transits,
            )
        except InsufficientBirthData:
            raise FactToolUnavailable(query.tool, "insufficient_birth_data") from None
        except ChartEngineUnavailable:
            raise FactToolUnavailable(query.tool, "chart_engine_unavailable") from None
        return bundle.all

    # -- panchang ----------------------------------------------------------

    def _resolve_place(self, query: FactQuery):  # noqa: ANN202 — ResolvedPlace
        label = (query.slots or {}).get("place") or query.place_label or self._default_place
        if self._places is None:
            raise FactToolUnavailable(query.tool, "no_place_resolver")
        try:
            return self._places.resolve_city(label)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            raise FactToolUnavailable(query.tool, "place_unresolved") from None

    def _local_date(self, query: FactQuery, place) -> dt.date:  # noqa: ANN001
        return query.now.astimezone(ZoneInfo(place.tz)).date()

    async def _panchang_day(self, query: FactQuery) -> Sequence[FactSnapshot]:
        if self._panchang is None:
            raise FactToolUnavailable(query.tool, "panchang_unavailable")
        place = self._resolve_place(query)
        result = await self._panchang.panchang(  # type: ignore[attr-defined]
            self._local_date(query, place), place, self._tradition
        )
        return result.facts

    async def _day_timings(self, query: FactQuery) -> Sequence[FactSnapshot]:
        if self._panchang is None:
            raise FactToolUnavailable(query.tool, "panchang_unavailable")
        place = self._resolve_place(query)
        result = await self._panchang.day_timings(  # type: ignore[attr-defined]
            self._local_date(query, place), place, self._tradition
        )
        return result.facts

    async def _muhurat(self, query: FactQuery) -> Sequence[FactSnapshot]:
        from sitara_schemas.facts import MuhuratType

        if self._panchang is None:
            raise FactToolUnavailable(query.tool, "panchang_unavailable")
        place = self._resolve_place(query)
        occasion = (query.slots or {}).get("occasion", "general")
        try:
            muhurat_type = MuhuratType(occasion)
        except ValueError:
            muhurat_type = MuhuratType.GENERAL
        start = self._local_date(query, place)
        result = await self._panchang.muhurat(  # type: ignore[attr-defined]
            muhurat_type, start, start + dt.timedelta(days=30), place, self._tradition
        )
        return result.facts

    # -- numerology --------------------------------------------------------

    async def _numerology_profile(self, query: FactQuery) -> Sequence[FactSnapshot]:
        # Numerology needs the confirmed name and date of birth, which live
        # behind the profile service; until the pipeline is handed a profile
        # loader it declines rather than computing from a partial record
        # (§22.10 — a name must be confirmed before it is summed).
        raise FactToolUnavailable(query.tool, "profile_loader_not_wired")
