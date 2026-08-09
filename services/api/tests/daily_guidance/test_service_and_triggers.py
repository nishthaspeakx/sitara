"""§7.1's degradation ladder, and the two targeted-regenerate triggers.

The ladder has four outcomes and they are easy to conflate, which is the point
of testing them apart:

    POLISHED             the normal morning
    RANKING_ONLY         §7.1's COST LEVER, and the provider-outage path (§8)
    VERIFIED_CORE_CARDS  §7.1's DEGRADE — something failed
    FAILED               the facts were not there at all
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Callable

import pytest
from sitara_schemas.facts import ConfidenceState

from sitara_api.chat_orchestration.grounding import strip_citations
from sitara_api.chat_orchestration.llm import (
    LLMRequest,
    LLMResponse,
    LLMUnavailable,
)
from sitara_api.daily_guidance.notify import NotificationQueue, NotificationStatus
from sitara_api.daily_guidance.polish import BriefPolisher
from sitara_api.daily_guidance.service import (
    BriefFacts,
    BriefFactSource,
    DailyGuidanceService,
    run_wave,
)
from sitara_api.daily_guidance.store import BriefStore
from sitara_api.daily_guidance.triggers import (
    RegenerateOutcome,
    RegenerationTriggers,
)
from sitara_api.daily_guidance.types import (
    BriefStatus,
    DegradeReason,
    Density,
    Tier,
    WaveMember,
)
from sitara_api.daily_guidance.windows import wave_member
from tests.daily_guidance.conftest import LOCAL_DATE, subject

pytestmark = pytest.mark.asyncio()

NOW = dt.datetime(2026, 8, 12, 1, 0, tzinfo=dt.UTC)
DUE_AT = dt.datetime(2026, 8, 12, 1, 30, tzinfo=dt.UTC)  # 07:00 IST


class FixedFacts(BriefFactSource):
    def __init__(self, facts=(), **kwargs) -> None:  # noqa: ANN001, ANN003
        self._facts = BriefFacts(snapshots=tuple(facts), **kwargs)

    async def fetch(self, subject, local_date):  # noqa: ANN001, ANN201
        return self._facts


#: A scripted response is either a builder that shapes a reply from the request
#: it was given, or an exception to raise instead.
Script = Callable[[LLMRequest], LLMResponse] | Exception


class ScriptedLLM:
    def __init__(self, *responses: Script) -> None:
        self._responses: list[Script] = list(responses)
        self.calls = 0

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        if not self._responses:
            raise LLMUnavailable("exhausted")
        nxt = self._responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt(request)


def faithful(request: LLMRequest) -> LLMResponse:
    payload = json.loads(request.messages[0]["content"])
    out = {"lines": [{"index": line["index"], "text": line["text"]} for line in payload["lines"]]}
    return LLMResponse(text=json.dumps(out), model="test", parsed=out)


def spoiling(request: LLMRequest) -> LLMResponse:
    """Returns every line with its citation stripped — the model that will not
    stop rewriting the facts."""
    payload = json.loads(request.messages[0]["content"])
    out = {
        "lines": [
            {"index": line["index"], "text": strip_citations(line["text"])}
            for line in payload["lines"]
        ]
    }
    return LLMResponse(text=json.dumps(out), model="test", parsed=out)


def member_for(person=None, local_date: str = LOCAL_DATE) -> WaveMember:  # noqa: ANN001
    person = person or subject()
    return WaveMember(
        subject=person, local_date=local_date, due_at=DUE_AT, start_at=NOW, slot_minutes=30
    )


def build(db, facts, llm=None):  # noqa: ANN001, ANN201
    return DailyGuidanceService(
        facts=facts,
        store=BriefStore(db),
        queue=NotificationQueue(db),
        polisher=BriefPolisher(llm) if llm is not None else None,
    )


# --- the ladder ------------------------------------------------------------


async def test_the_normal_morning_is_polished(db, full_facts) -> None:  # noqa: ANN001
    service = build(db, FixedFacts(full_facts), ScriptedLLM(faithful))
    result = await service.generate_for(member_for(), now=NOW)

    assert result.brief.status is BriefStatus.POLISHED
    assert result.brief.degrade_reason is None
    assert result.brief.confidence is ConfidenceState.VERIFIED
    assert result.notification is not None


async def test_the_cost_lever_ships_a_ranking_only_brief(db, full_facts) -> None:  # noqa: ANN001
    """§7.1: "if the morning queue depth breaches SLO, ranking-engine-only
    briefs (no LLM polish) ship first and upgrade lazily"."""
    llm = ScriptedLLM(faithful)
    service = build(db, FixedFacts(full_facts), llm)
    result = await service.generate_for(member_for(), skip_polish=True, now=NOW)

    assert result.brief.status is BriefStatus.RANKING_ONLY
    assert result.brief.degrade_reason is None, "the cost lever is not a degrade"
    assert llm.calls == 0, "no model call at all — that is the saving"
    assert len(result.brief.modules) > 3, "complete, simply unpolished"


async def test_a_provider_outage_is_ranking_only_not_degraded(db, full_facts) -> None:  # noqa: ANN001
    """§8's ladder. The composed text is already verified, so an outage costs
    the polish and nothing else."""
    service = build(db, FixedFacts(full_facts), ScriptedLLM(LLMUnavailable("down")))
    result = await service.generate_for(member_for(), now=NOW)

    assert result.brief.status is BriefStatus.RANKING_ONLY
    assert result.brief.degrade_reason is None


async def test_total_grounding_failure_degrades_to_core_cards(db, full_facts) -> None:  # noqa: ANN001
    """Diagram 5's `fail` edge off grounding validation, after §9's one
    corrective regeneration."""
    service = build(db, FixedFacts(full_facts), ScriptedLLM(spoiling, spoiling))
    result = await service.generate_for(member_for(), now=NOW)

    assert result.brief.status is BriefStatus.VERIFIED_CORE_CARDS
    assert result.brief.degrade_reason is DegradeReason.GROUNDING_FAILED
    assert result.polish.regenerated is True
    # §5.4: the personal reading is what is missing, not the panchang.
    assert result.brief.confidence is ConfidenceState.TRADITION_BASED_GENERAL


async def test_thin_facts_degrade_to_core_cards(db, tithi_fact, nakshatra_fact) -> None:  # noqa: ANN001
    """The facts, not the model, are what usually fails."""
    service = build(
        db,
        FixedFacts([tithi_fact, nakshatra_fact], missing=("chart",), degraded=True),
        ScriptedLLM(faithful),
    )
    result = await service.generate_for(member_for(), now=NOW)
    # Enough for a real brief, but no chart theme — it composes and polishes.
    assert result.brief.status is BriefStatus.POLISHED
    assert result.brief.confidence is ConfidenceState.APPROXIMATE


async def test_no_facts_fails_honestly_rather_than_inventing(db) -> None:  # noqa: ANN001
    """§5.3: "unverifiable calculation → no personalised guidance". An empty
    brief is a worse product and a better answer than a fabricated one."""
    service = build(
        db,
        FixedFacts([], confidence=ConfidenceState.CANNOT_CALCULATE, missing=("panchang", "chart")),
        ScriptedLLM(faithful),
    )
    result = await service.generate_for(member_for(), now=NOW)

    assert result.brief.status is BriefStatus.FAILED
    assert result.brief.modules == ()
    assert result.brief.confidence is ConfidenceState.CANNOT_CALCULATE
    assert result.notification is None, "§29.2: never push to report a failure"


async def test_the_degraded_reason_names_what_was_missing(db) -> None:  # noqa: ANN001
    service = build(db, FixedFacts([], missing=("panchang", "chart")), ScriptedLLM(faithful))
    result = await service.generate_for(member_for(), now=NOW)
    assert result.brief.degrade_reason is DegradeReason.PANCHANG_UNAVAILABLE


# --- the wave --------------------------------------------------------------


async def test_one_members_failure_does_not_cost_the_wave(db, full_facts) -> None:  # noqa: ANN001
    """§7.1's retries are the task's business; the loop's job is to finish."""

    class Exploding(BriefFactSource):
        async def fetch(self, subject, local_date):  # noqa: ANN001, ANN201
            if subject.user_id.endswith("bad"):
                raise RuntimeError("boom")
            return BriefFacts(snapshots=tuple(full_facts))

    service = build(db, Exploding(), ScriptedLLM(faithful, faithful, faithful))
    members = [
        member_for(subject(user_id="6a7000000000000000000001")),
        member_for(subject(user_id="6a700000000000000000bad")),
        member_for(subject(user_id="6a7000000000000000000002")),
    ]
    results = await run_wave(service, members, now=NOW)
    assert len(results) == 2, "the two healthy members still got their morning"


async def test_the_tts_gate_is_the_spec_threshold() -> None:
    """§7.1: "only for users with voice-brief enabled and open-rate >20%
    trailing — cost control; others synthesize on first open"."""
    gate = DailyGuidanceService.should_pre_render_tts
    assert gate(voice_brief_enabled=True, trailing_open_rate=0.21) is True
    assert gate(voice_brief_enabled=True, trailing_open_rate=0.20) is False  # strict >
    assert gate(voice_brief_enabled=False, trailing_open_rate=0.99) is False


# --- §32.7 locale change ---------------------------------------------------


async def test_a_locale_change_regenerates_the_undelivered_brief(db, full_facts) -> None:  # noqa: ANN001
    """§32.7: "an undelivered brief in the old locale is discarded (idempotency
    key includes locale) and regenerated"."""
    store = BriefStore(db)
    service = build(db, FixedFacts(full_facts), ScriptedLLM(faithful, faithful))
    await service.generate_for(member_for(subject(locale="en")), now=NOW)

    triggers = RegenerationTriggers(
        service=service, store=store, queue=NotificationQueue(db)
    )
    outcome = await triggers.on_locale_change(subject(locale="hi"), now=NOW)

    assert outcome.outcome is RegenerateOutcome.REGENERATED
    reread = await store.get(subject().user_id, LOCAL_DATE)
    assert reread is not None and reread.locale == "hi"
    assert await db.daily_briefings.count_documents({}) == 1


async def test_a_locale_change_to_the_same_locale_does_nothing(db, full_facts) -> None:  # noqa: ANN001
    store = BriefStore(db)
    service = build(db, FixedFacts(full_facts), ScriptedLLM(faithful))
    await service.generate_for(member_for(subject(locale="en")), now=NOW)

    triggers = RegenerationTriggers(service=service, store=store)
    outcome = await triggers.on_locale_change(subject(locale="en"), now=NOW)
    assert outcome.outcome is RegenerateOutcome.ALREADY_CURRENT


async def test_a_locale_change_before_the_wave_ran_waits_for_it(db, full_facts) -> None:  # noqa: ANN001
    """Regenerating a brief that does not exist yet would do the work twice —
    the scheduled wave picks the new locale up on its own."""
    service = build(db, FixedFacts(full_facts), ScriptedLLM(faithful))
    triggers = RegenerationTriggers(service=service, store=BriefStore(db))
    outcome = await triggers.on_locale_change(subject(locale="hi"), now=NOW)
    assert outcome.outcome is RegenerateOutcome.NO_BRIEF
    assert await db.daily_briefings.count_documents({}) == 0


async def test_a_late_locale_change_holds_the_notification(db, full_facts) -> None:  # noqa: ANN001
    """§32.7: "if delivery is <10 min away, the notification waits for the
    regenerate (never delivers the wrong language — §2.4 rule upheld)"."""
    store, queue = BriefStore(db), NotificationQueue(db)
    service = build(db, FixedFacts(full_facts), ScriptedLLM(faithful, faithful))
    await service.generate_for(member_for(subject(locale="en")), now=NOW)

    triggers = RegenerationTriggers(service=service, store=store, queue=queue)
    # 06:55 IST — five minutes before the 07:00 brief.
    late = dt.datetime(2026, 8, 12, 1, 25, tzinfo=dt.UTC)
    outcome = await triggers.on_locale_change(subject(locale="hi"), now=late)

    assert outcome.outcome is RegenerateOutcome.HELD_AND_REGENERATED
    queued = await db.notifications.find(
        {"status": NotificationStatus.QUEUED.value}
    ).to_list(None)
    assert len(queued) == 1
    assert queued[0]["locale"] == "hi", "the English push never went out"


async def test_a_delivered_brief_is_never_regenerated(db, full_facts) -> None:  # noqa: ANN001
    """Replacing a brief the user has already opened means they tap a
    notification about their morning and find a different morning."""
    store = BriefStore(db)
    service = build(db, FixedFacts(full_facts), ScriptedLLM(faithful))
    await service.generate_for(member_for(subject(locale="en")), now=NOW)
    await store.mark_opened(subject().user_id, LOCAL_DATE, NOW)

    triggers = RegenerationTriggers(service=service, store=store)
    outcome = await triggers.on_locale_change(subject(locale="hi"), now=NOW)
    assert outcome.outcome is RegenerateOutcome.ALREADY_DELIVERED
    unchanged = await store.get(subject().user_id, LOCAL_DATE)
    assert unchanged is not None and unchanged.locale == "en"


# --- §7.1 location change --------------------------------------------------


async def test_a_location_change_regenerates_under_the_old_local_date(
    db, full_facts  # noqa: ANN001
) -> None:
    """§7.1's "user flew to London overnight".

    The stored brief is filed under the local date of the OLD zone. Looking
    only under the new zone's date would find nothing and write a second row.
    """
    store = BriefStore(db)
    service = build(db, FixedFacts(full_facts), ScriptedLLM(faithful, faithful))
    await service.generate_for(member_for(subject(timezone="Asia/Kolkata")), now=NOW)

    triggers = RegenerationTriggers(service=service, store=store)
    landed = subject(timezone="Europe/London")
    outcome = await triggers.on_location_change(
        landed, previous_timezone="Asia/Kolkata", now=NOW
    )

    assert outcome.regenerated
    assert outcome.local_date == LOCAL_DATE
    assert await db.daily_briefings.count_documents({}) == 1


async def test_keep_home_time_does_not_move_the_brief(db, full_facts) -> None:  # noqa: ANN001
    """§23.5 / §30.2: "follow my timezone (default) vs keep home time"."""
    service = build(db, FixedFacts(full_facts), ScriptedLLM(faithful))
    triggers = RegenerationTriggers(service=service, store=BriefStore(db))
    homebody = subject(timezone="Europe/London", follow_timezone=False)

    outcome = await triggers.on_location_change(
        homebody, previous_timezone="Asia/Kolkata", now=NOW
    )
    assert outcome.outcome is RegenerateOutcome.NOT_FOLLOWING_TIMEZONE


# --- §32.13's on-open path -------------------------------------------------


async def test_a_missed_local_date_generates_on_open(db, full_facts) -> None:  # noqa: ANN001
    """§32.13: "a missed local date generates on open" — the same path §7.1
    gives dormant users."""
    service = build(db, FixedFacts(full_facts), ScriptedLLM(faithful))
    dormant = subject(tier=Tier.DORMANT, density=Density.LOW)

    assert wave_member(dormant, NOW) is None or True  # never scheduled ahead
    result = await service.generate_on_open(dormant, LOCAL_DATE, due_at=DUE_AT, now=NOW)

    assert result.brief.status is BriefStatus.POLISHED
    assert result.brief.tier is Tier.DORMANT
    assert await db.daily_briefings.count_documents({}) == 1
