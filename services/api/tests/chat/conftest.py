"""Chat-orchestration test harness.

No Mongo, no network: the store and the review queue are in-memory and the LLM
is scripted. The point of these tests is that the VALIDATORS hold, so the model
has to be a thing we control precisely rather than a thing we hope behaves.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest
from sitara_schemas.facts import (
    FactKind,
    FactMethod,
    FactPrecision,
    FactSnapshot,
    Graha,
    HouseAssignmentValue,
    TzMethod,
    build_fact_id,
)

from sitara_api.chat_orchestration.config import ChatSettings
from sitara_api.chat_orchestration.facts import FactQuery
from sitara_api.chat_orchestration.grounding import GroundingValidator
from sitara_api.chat_orchestration.intent import IntentRouter
from sitara_api.chat_orchestration.langquality import LanguageQualityValidator
from sitara_api.chat_orchestration.llm import LLMRequest, LLMResponse, LLMUnavailable
from sitara_api.chat_orchestration.memory import NullMemoryRetriever, NullMemorySuggester
from sitara_api.chat_orchestration.pipeline import ChatPipeline
from sitara_api.chat_orchestration.safety import FearSellingLint, SafetyPreCheck
from sitara_api.chat_orchestration.store import InMemoryMessageStore, InMemoryReviewQueue
from sitara_api.chat_orchestration.tracing import MemorySink
from sitara_api.chat_orchestration.types import (
    BirthProfile,
    FactTool,
    Stage,
    TurnRequest,
    ValidatedFacts,
)

NOW = dt.datetime(2026, 8, 8, 9, 30, tzinfo=dt.UTC)
# §33.2: the product identity IS the Mongo _id, and §6.4 types every reference
# to it as objectId. Fixtures use real ids so the in-memory tests exercise the
# same values the collection validators will see.
USER_ID = "6a70000000000000000000a1"
CONVERSATION_ID = "6a70000000000000000000c1"
IST = TzMethod(tz="Asia/Kolkata", utc_offset_seconds=19800)

SATURN_FACT_ID = build_fact_id("transit.saturn.house", "2026-08-08", USER_ID, 1)
VENUS_FACT_ID = build_fact_id("transit.venus.house", "2026-08-08", USER_ID, 1)


def transit_house_fact(graha: Graha, house: int, fact_id: str) -> FactSnapshot:
    """One transit-house snapshot, valid for the whole of 2026-08-08 UTC."""
    return FactSnapshot(
        fact_id=fact_id,
        kind=FactKind.TRANSIT_GRAHA_HOUSE,
        value=HouseAssignmentValue(graha=graha, whole_sign_house=house, bhava=house),
        precision=FactPrecision(tolerance=0, unit="exact"),
        method=FactMethod(ayanamsa="lahiri", house_presentation="whole_sign", tz=IST),
        valid_from=dt.datetime(2026, 8, 8, 0, 0, tzinfo=dt.UTC),
        valid_to=dt.datetime(2026, 8, 8, 23, 59, tzinfo=dt.UTC),
        engine_semver="0.1.0",
        data_revision="test",
    )


@pytest.fixture()
def saturn_facts() -> ValidatedFacts:
    return ValidatedFacts(
        snapshots=(transit_house_fact(Graha.SATURN, 10, SATURN_FACT_ID),)
    )


@pytest.fixture()
def validator() -> GroundingValidator:
    return GroundingValidator()


# --------------------------------------------------------------------------
# A scripted LLM
# --------------------------------------------------------------------------

_CLEAR_SAFETY = {
    "scores": {
        "self_harm": 0.0,
        "medical": 0.0,
        "legal": 0.0,
        "financial_risk": 0.0,
        "minors": 0.0,
        "abuse": 0.0,
        "emotional_distress": 0.0,
        "acute_crisis": 0.0,
    },
    "overall_flag": False,
}

_TRANSIT_INTENT = {
    "intent": "natal_chart_question",
    "confidence": 0.9,
    "tools": ["transits"],
    "slots": {},
}


class ScriptedLLM:
    """Returns queued responses per request label; defaults for the rest.

    An unscripted label with no default raises rather than inventing a reply —
    a test that silently exercised a different path than it meant to would be
    worse than a failing one.
    """

    def __init__(self) -> None:
        self.defaults: dict[str, Any] = {
            "safety.l1": _CLEAR_SAFETY,
            "intent.route": _TRANSIT_INTENT,
            "summary.rolling": "",
        }
        self.queues: dict[str, list[Any]] = {}
        self.calls: list[LLMRequest] = []

    def script(self, label: str, *responses: Any) -> None:
        self.queues.setdefault(label, []).extend(responses)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        queue = self.queues.get(request.label)
        if queue:
            payload = queue.pop(0)
        elif request.label in self.defaults:
            payload = self.defaults[request.label]
        else:
            raise AssertionError(f"unscripted LLM call: {request.label!r}")

        if isinstance(payload, Exception):
            raise payload
        if isinstance(payload, LLMResponse):
            # Lets a test script an adapter-level condition — a truncated
            # reply, a fallback-provider response — not just a body.
            return payload
        text = payload if isinstance(payload, str) else json.dumps(payload)
        return LLMResponse(
            text=text,
            model="scripted",
            parsed=payload if isinstance(payload, dict) else None,
            input_tokens=100,
            output_tokens=50,
        )


class StubFactProvider:
    """Serves a fixed snapshot set for the tools it is given."""

    def __init__(self, by_tool: dict[FactTool, Sequence[FactSnapshot]]) -> None:
        self._by_tool = by_tool
        self.calls: list[FactTool] = []

    async def fetch(self, query: FactQuery) -> Sequence[FactSnapshot]:
        self.calls.append(query.tool)
        return self._by_tool.get(query.tool, ())


class TraceProbe:
    """Reads the Langfuse-shaped events a MemorySink collected."""

    def __init__(self, sink: MemorySink) -> None:
        self.sink = sink

    def spans_for(self, stage: Stage) -> list[dict[str, Any]]:
        return [event for event in self.sink.events if event.get("stage") == stage.value]

    @property
    def events(self) -> list[dict[str, Any]]:
        return self.sink.events


@dataclass
class PipelineEnv:
    pipeline: ChatPipeline
    llm: ScriptedLLM
    store: InMemoryMessageStore
    review_queue: InMemoryReviewQueue
    trace: TraceProbe
    provider: StubFactProvider
    profile: BirthProfile = field(
        default_factory=lambda: BirthProfile(
            has_date=True, has_exact_time=True, has_place=True, tz="Asia/Kolkata"
        )
    )
    locale: str = "en"


def build_env(
    *,
    facts_by_tool: dict[FactTool, Sequence[FactSnapshot]] | None = None,
    settings: ChatSettings | None = None,
    classifier_enabled: bool = True,
) -> PipelineEnv:
    chat_settings = settings or ChatSettings(
        anthropic_api_key="test-key",
        safety_classifier_enabled=classifier_enabled,
    )
    llm = ScriptedLLM()
    store = InMemoryMessageStore()
    review_queue = InMemoryReviewQueue()
    sink = MemorySink()
    provider = StubFactProvider(
        facts_by_tool
        if facts_by_tool is not None
        else {FactTool.TRANSITS: (transit_house_fact(Graha.SATURN, 10, SATURN_FACT_ID),)}
    )
    pipeline = ChatPipeline(
        settings=chat_settings,
        llm=llm,
        safety_pre=SafetyPreCheck(chat_settings, llm),
        fear_lint=FearSellingLint(),
        intent_router=IntentRouter(chat_settings, llm),
        fact_provider=provider,
        grounding=GroundingValidator(),
        langquality=LanguageQualityValidator(),
        memory_retriever=NullMemoryRetriever(),
        memory_suggester=NullMemorySuggester(),
        store=store,
        review_queue=review_queue,
        trace_sink=sink,
    )
    return PipelineEnv(
        pipeline=pipeline,
        llm=llm,
        store=store,
        review_queue=review_queue,
        trace=TraceProbe(sink),
        provider=provider,
    )


@pytest.fixture()
def pipeline_env() -> PipelineEnv:
    return build_env()


async def run_turn(env: PipelineEnv, text: str, **overrides: Any):  # noqa: ANN201
    request = TurnRequest(
        user_id=USER_ID,
        conversation_id=CONVERSATION_ID,
        text=text,
        locale=overrides.pop("locale", env.locale),
        now=overrides.pop("now", NOW),
        profile=overrides.pop("profile", env.profile),
        place_label=overrides.pop("place_label", "Delhi"),
        **overrides,
    )
    return await env.pipeline.run(request)


__all__ = [
    "CONVERSATION_ID",
    "NOW",
    "SATURN_FACT_ID",
    "USER_ID",
    "VENUS_FACT_ID",
    "LLMUnavailable",
    "PipelineEnv",
    "ScriptedLLM",
    "StubFactProvider",
    "build_env",
    "run_turn",
    "transit_house_fact",
]
