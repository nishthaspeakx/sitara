"""chat-orchestration — the §9 pipeline (SPEC §6.3 bounded context).

Import surface for the rest of the service. Wiring lives in `build_pipeline`
so the app factory does not have to know the shape of nine collaborators.
"""

from __future__ import annotations

from typing import Any

from sitara_api.chat_orchestration.config import ChatSettings
from sitara_api.chat_orchestration.facts import AstrologyFacadeProvider, FactProvider
from sitara_api.chat_orchestration.grounding import GroundingValidator, GroundingVerdict
from sitara_api.chat_orchestration.intent import IntentRouter
from sitara_api.chat_orchestration.langquality import LanguageQualityValidator
from sitara_api.chat_orchestration.llm import LLMClient, build_llm
from sitara_api.chat_orchestration.memory import NullMemoryRetriever, NullMemorySuggester
from sitara_api.chat_orchestration.pipeline import ChatPipeline
from sitara_api.chat_orchestration.safety import FearSellingLint, SafetyPreCheck
from sitara_api.chat_orchestration.store import MongoMessageStore, MongoReviewQueue
from sitara_api.chat_orchestration.tracing import build_tracer
from sitara_api.chat_orchestration.types import TurnRequest, TurnResult

__all__ = [
    "ChatPipeline",
    "ChatSettings",
    "FactProvider",
    "GroundingValidator",
    "GroundingVerdict",
    "TurnRequest",
    "TurnResult",
    "build_pipeline",
]


def build_pipeline(
    *,
    chat_settings: ChatSettings,
    environment: str,
    db: Any,
    panchang_service: Any = None,
    numerology_adapter: Any = None,
    place_resolver: Any = None,
    llm: LLMClient | None = None,
    memory_retriever: Any = None,
    astrology_facade: Any = None,
) -> ChatPipeline | None:
    """Wire the pipeline once, at app start. None when chat cannot run.

    A blank model key is not a crash: it is the §8 ladder's "provider down"
    state, the same way a blank DivineAPI key is. The service still boots and
    every other module still serves; `/v1/chat/turn` returns the §34.4
    SYS_UNAVAILABLE envelope until a key exists. An app that refused to start
    would take the morning brief down with it.

    `llm` is injectable so a test — or a deployment that pins a different
    provider behind the same interface (§9) — never has to reach past this
    function into a stage.
    """
    if llm is None and not chat_settings.anthropic_api_key:
        return None
    router_llm = llm or build_llm(chat_settings)
    sink, capture = build_tracer(
        environment=environment,
        capture_content=chat_settings.trace_capture_content,
        langfuse_enabled=chat_settings.langfuse_enabled,
    )
    return ChatPipeline(
        settings=chat_settings,
        llm=router_llm,
        safety_pre=SafetyPreCheck(chat_settings, router_llm),
        fear_lint=FearSellingLint(),
        intent_router=IntentRouter(chat_settings, router_llm),
        fact_provider=AstrologyFacadeProvider(
            panchang_service=panchang_service,
            numerology_adapter=numerology_adapter,
            place_resolver=place_resolver,
            # §13's single door to birth details. Without it every chart tool
            # declines `chart_facade_unavailable`, which the pipeline renders
            # as `chat.data.cannot_calculate` — so chat answered EVERY natal,
            # transit and relationship question with "I don't have enough to
            # work this out" while the engine sat healthy on :8003 and the
            # user's birth row sat complete in Mongo. The provider has taken
            # this argument since M5; nothing ever passed it, and no test
            # noticed because the chat suite stubs the provider outright.
            astrology_facade=astrology_facade,
        ),
        grounding=GroundingValidator(),
        langquality=LanguageQualityValidator(),
        # M5-P6b: the real §32.5 retriever. `NullMemoryRetriever` remains the
        # fallback for a deployment with no embedding provider — answering
        # without remembered context is a degradation, not an outage.
        memory_retriever=memory_retriever or NullMemoryRetriever(),
        memory_suggester=NullMemorySuggester(),
        store=MongoMessageStore(db),
        review_queue=MongoReviewQueue(db),
        trace_sink=sink,
        capture_content=capture,
    )
