"""The model-abstraction layer (§9).

§9 asks for "a thin model-abstraction layer (LiteLLM-style adapter, ours) that
pins versions, routes by task, and enables a fallback provider (secondary
frontier model) behind the same interface". This is it: one `LLMClient`
protocol, one request shape, and adapters behind it.

Two things stages are NOT allowed to do, and cannot do through this interface:
name a model, or reach a vendor SDK. They declare a task and a temperature;
routing, pinning, caching and fallback happen here.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from sitara_schemas import ErrorCode

from sitara_api.chat_orchestration.config import ChatSettings
from sitara_api.errors import ApiError

logger = logging.getLogger(__name__)


class LLMTask(StrEnum):
    """§9's routing dimension. CONVERSATION is Sonnet-class; the rest are
    Haiku-class "classification/ranking polish"."""

    CONVERSATION = "conversation"
    CLASSIFICATION = "classification"
    SUMMARY = "summary"


@dataclass(frozen=True)
class LLMRequest:
    """`system` is the STABLE PREFIX — persona + locale style guide (§9).

    It is a tuple of blocks so the adapter can put the cache breakpoint on the
    last one. Anything that varies per turn belongs in `messages`, after the
    breakpoint; a timestamp in `system` would invalidate the cache for every
    user on every turn.
    """

    task: LLMTask
    system: tuple[str, ...]
    messages: tuple[dict[str, Any], ...]
    temperature: float
    max_tokens: int
    #: JSON Schema. Present for §9's four structured-output uses: intent
    #: routing, memory-chip extraction, safety labels, presence-state tags.
    schema: dict[str, Any] | None = None
    #: Trace label, e.g. "intent.route". Never contains user content.
    label: str = ""
    #: How many leading `system` blocks are STABLE and therefore cacheable.
    #: The breakpoint goes after this many blocks, not simply on the last one:
    #: a per-turn block (the safety register) below the breakpoint would make
    #: every constrained turn a cache write instead of a read. None = all.
    cacheable_prefix_len: int | None = None


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    parsed: dict[str, Any] | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    #: True when the model hit `max_tokens` mid-reply (§9's per-turn hard cap).
    truncated: bool = False
    #: What the adapter actually sent, when it could not send what was asked
    #: for (see `_supports_sampling`). Surfaced in the trace, never silent.
    applied: dict[str, Any] = field(default_factory=dict)


class LLMUnavailable(Exception):
    """Every rung of the model ladder failed. §8 degradation takes over."""


class LLMClient(Protocol):
    async def complete(self, request: LLMRequest) -> LLMResponse: ...


# --------------------------------------------------------------------------
# Model capabilities
# --------------------------------------------------------------------------

#: Model families that reject a non-default `temperature`/`top_p`/`top_k`
#: with a 400. §9 fixes our temperatures (0.2 guidance / 0.7 small talk); on
#: these models the adapter cannot send them, so it records what it applied
#: instead of pretending. Recorded as an open question for §31.3 change
#: control — see docs/spec/SPEC.md §9 and the M5 change-control entry.
_SAMPLING_REJECTED: tuple[str, ...] = (
    "claude-opus-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-sonnet-5",
    "claude-fable-5",
    "claude-mythos-5",
)


def _supports_sampling(model: str) -> bool:
    return not any(model.startswith(prefix) for prefix in _SAMPLING_REJECTED)


def estimate_tokens(text: str) -> int:
    """Cheap local estimate for budget decisions only (§9 token budgets).

    Deliberately not `messages.count_tokens` — that is a network round trip,
    and the rolling-summary trigger must not add one to every turn. Accounting
    uses the real `usage` numbers off each response; this only decides when to
    summarise, where being approximately right early is the point.
    """
    return max(1, len(text) // 3)


# --------------------------------------------------------------------------
# The Anthropic adapter
# --------------------------------------------------------------------------


class AnthropicLLM:
    """One pinned model, one task tier. Construct one per tier via `build_llm`."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None,
        timeout_seconds: float,
        max_retries: int,
        effort: str | None = None,
        thinking: str = "disabled",
    ) -> None:
        # Imported lazily so a deployment that never enables chat (or a unit
        # test with a scripted client) does not need the SDK configured.
        from anthropic import AsyncAnthropic

        self.model = model
        self._effort = effort
        self._thinking = thinking
        self._client = AsyncAnthropic(
            api_key=api_key, timeout=timeout_seconds, max_retries=max_retries
        )

    async def complete(self, request: LLMRequest) -> LLMResponse:
        import anthropic

        system = self._system_blocks(request.system, request.cacheable_prefix_len)
        output_config: dict[str, Any] = {}
        if self._effort:
            output_config["effort"] = self._effort
        if request.schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": request.schema}

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": request.max_tokens,
            "system": system,
            "messages": list(request.messages),
        }
        if output_config:
            kwargs["output_config"] = output_config
        if self._thinking == "disabled":
            # §8's chat SLO is first token p95 < 1.8s. Adaptive thinking is on
            # by default on the pinned Sonnet-class model and would spend the
            # per-turn cap before a word reached the user; grounding is
            # enforced mechanically downstream, not by the model deliberating.
            kwargs["thinking"] = {"type": "disabled"}

        applied: dict[str, Any] = {"model": self.model, "thinking": self._thinking}
        if _supports_sampling(self.model):
            kwargs["temperature"] = request.temperature
            applied["temperature"] = request.temperature
        else:
            applied["temperature"] = None
            applied["temperature_declared"] = request.temperature
            applied["temperature_note"] = "model rejects sampling parameters"

        try:
            message = await self._client.messages.create(**kwargs)
        except anthropic.APIStatusError as exc:
            logger.warning("llm call failed label=%s status=%s", request.label, exc.status_code)
            raise LLMUnavailable(request.label) from None
        except anthropic.APIError:
            logger.warning("llm call failed label=%s (transport)", request.label)
            raise LLMUnavailable(request.label) from None

        if message.stop_reason == "refusal":
            # A model-side decline is a safety outcome, not a crash. The
            # caller falls back to a template rather than surfacing nothing.
            logger.info("llm refused label=%s", request.label)
            raise LLMUnavailable(f"{request.label}:refusal")

        text = "".join(block.text for block in message.content if block.type == "text")
        parsed = None
        if request.schema is not None:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                raise LLMUnavailable(f"{request.label}:unparseable") from None

        usage = message.usage
        return LLMResponse(
            text=text,
            model=message.model,
            parsed=parsed,
            # A draft cut off at the cap loses its trailing citation and would
            # fail grounding for the wrong reason. Saying so lets the caller
            # spend its one regeneration on brevity instead of on citations.
            truncated=message.stop_reason == "max_tokens",
            input_tokens=usage.input_tokens or 0,
            output_tokens=usage.output_tokens or 0,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            applied=applied,
        )

    @staticmethod
    def _system_blocks(
        blocks: tuple[str, ...], cacheable_prefix_len: int | None = None
    ) -> list[dict[str, Any]]:
        """Persona + locale style guide are stable prefixes — cache them (§9).

        The breakpoint caches everything up to and including the block it sits
        on, so it goes after the last STABLE block. Putting it on the last
        block outright would place a per-turn safety register inside the cached
        prefix, and every constrained turn would write a fresh entry rather
        than read the persona. Below the model's minimum cacheable prefix
        nothing is written and nothing errors; the marker is simply inert.
        """
        rendered: list[dict[str, Any]] = [
            {"type": "text", "text": block} for block in blocks if block
        ]
        if not rendered:
            return rendered
        limit = len(rendered) if cacheable_prefix_len is None else cacheable_prefix_len
        index = max(0, min(limit, len(rendered)) - 1)
        rendered[index]["cache_control"] = {"type": "ephemeral"}
        return rendered


class FallbackLLM:
    """§9's "fallback provider behind the same interface".

    §8: "Claude primary down → fallback model with conservative persona
    prompt". Conservative is not a different persona file — it is a lower
    temperature and the same validators, which still gate the output.
    """

    def __init__(self, primary: LLMClient, secondary: LLMClient) -> None:
        self._primary = primary
        self._secondary = secondary

    async def complete(self, request: LLMRequest) -> LLMResponse:
        try:
            return await self._primary.complete(request)
        except LLMUnavailable:
            logger.warning("primary model unavailable label=%s — falling back", request.label)
            conservative = LLMRequest(
                task=request.task,
                system=request.system,
                messages=request.messages,
                temperature=min(request.temperature, 0.2),
                max_tokens=request.max_tokens,
                schema=request.schema,
                label=f"{request.label}.fallback",
            )
            response = await self._secondary.complete(conservative)
            return LLMResponse(
                **{
                    **response.__dict__,
                    "applied": {**response.applied, "fallback_provider": True},
                }
            )


class TaskRouter:
    """Routes by task to a pinned model (§9). The only place a stage's
    `LLMTask` becomes a model id."""

    def __init__(self, by_task: dict[LLMTask, LLMClient]) -> None:
        self._by_task = by_task

    async def complete(self, request: LLMRequest) -> LLMResponse:
        client = self._by_task.get(request.task)
        if client is None:
            raise LLMUnavailable(f"no client routed for task {request.task}")
        return await client.complete(request)


def build_llm(settings: ChatSettings) -> TaskRouter:
    """Wire the §9 tiers. Called once at app start, never per turn."""

    def anthropic_client(model: str, effort: str, thinking: str) -> AnthropicLLM:
        return AnthropicLLM(
            model=model,
            api_key=settings.anthropic_api_key,
            timeout_seconds=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
            effort=effort,
            thinking=thinking,
        )

    conversation: LLMClient = anthropic_client(settings.conversation_model, "medium", "disabled")
    if settings.fallback_conversation_model:
        conversation = FallbackLLM(
            conversation,
            anthropic_client(settings.fallback_conversation_model, "medium", "disabled"),
        )
    classification = anthropic_client(settings.classification_model, "low", "disabled")

    return TaskRouter(
        {
            LLMTask.CONVERSATION: conversation,
            LLMTask.CLASSIFICATION: classification,
            LLMTask.SUMMARY: classification,
        }
    )


def unavailable_error() -> ApiError:
    return ApiError(ErrorCode.SYS_UNAVAILABLE, "errors.sys.unavailable")
