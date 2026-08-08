"""The mandatory per-turn pipeline (§9).

    input → language/script detection → safety pre-check → intent routing →
    required-data check → memory retrieval ∥ fact tool-calls → fact validation
    → response generation → grounding check → language-quality check →
    safety post-check → TTS render → presence state events → transcript store
    → memory-chip suggestion

Every stage below appears in that order and nowhere else. Three properties are
worth stating because they are what the sequence is FOR:

* The model is never the last word. Generation sits in the middle; three
  validators sit after it, and a draft that fails them does not reach a person
  regardless of how good it looked.
* One corrective regeneration, then the safe fallback line and the human
  review queue. Not two, not a loop (§9, §2.4 rule 8).
* An L4 turn never reaches the model at all. §22.9: "L4 auto-response
  (helplines, no astrology) is instant and machine-delivered".
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from dataclasses import dataclass

from sitara_schemas.facts import ConfidenceState

from sitara_api import localisation
from sitara_api.chat_orchestration import memory as memory_mod
from sitara_api.chat_orchestration import prompts, required_data
from sitara_api.chat_orchestration.budget import ContextBudget, daily_cap_notice
from sitara_api.chat_orchestration.config import ChatSettings
from sitara_api.chat_orchestration.facts import (
    FactContext,
    FactProvider,
    gather_facts,
    validate,
)
from sitara_api.chat_orchestration.grounding import GroundingValidator
from sitara_api.chat_orchestration.intent import IntentRouter
from sitara_api.chat_orchestration.langquality import LanguageQualityValidator
from sitara_api.chat_orchestration.language import detect
from sitara_api.chat_orchestration.llm import (
    LLMClient,
    LLMRequest,
    LLMTask,
    LLMUnavailable,
)
from sitara_api.chat_orchestration.safety import (
    FearSellingLint,
    SafetyPreCheck,
    check_no_prompt_leak,
)
from sitara_api.chat_orchestration.store import (
    MessageStore,
    ReviewEntry,
    ReviewQueue,
    build_guidance_log,
    build_message,
    pseudonymise,
)
from sitara_api.chat_orchestration.tracing import TraceSink, TurnTrace
from sitara_api.chat_orchestration.types import (
    Intent,
    MemoryChip,
    PresenceState,
    SafetyAssessment,
    SafetyLevel,
    Stage,
    TokenUsage,
    TurnRequest,
    TurnResult,
    ValidatedFacts,
)

logger = logging.getLogger(__name__)

#: Templated replies. §9 generates guidance; it does not generate a crisis
#: response, a decline, or the fallback line — those are authored copy,
#: reviewed per locale, and delivered verbatim.
KEY_CRISIS = "chat.safety.crisis"
KEY_FALLBACK = "chat.fallback.safe_line"
KEY_CANNOT_CALCULATE = "chat.data.cannot_calculate"
KEY_MISSING_BIRTH_DATE = "chat.data.missing.birth_date"
KEY_MISSING_BIRTH_PLACE = "chat.data.missing.birth_place"
KEY_MISSING_LOCATION = "chat.data.missing.current_location"

_MISSING_KEYS = {
    "birth_date": KEY_MISSING_BIRTH_DATE,
    "birth_place": KEY_MISSING_BIRTH_PLACE,
    "current_location": KEY_MISSING_LOCATION,
}


class ChatPipeline:
    def __init__(
        self,
        *,
        settings: ChatSettings,
        llm: LLMClient,
        safety_pre: SafetyPreCheck,
        fear_lint: FearSellingLint,
        intent_router: IntentRouter,
        fact_provider: FactProvider,
        grounding: GroundingValidator,
        langquality: LanguageQualityValidator,
        memory_retriever: memory_mod.MemoryRetriever,
        memory_suggester: memory_mod.MemorySuggester,
        store: MessageStore,
        review_queue: ReviewQueue,
        trace_sink: TraceSink,
        capture_content: bool = False,
    ) -> None:
        self._settings = settings
        self._llm = llm
        self._safety_pre = safety_pre
        self._fear_lint = fear_lint
        self._router = intent_router
        self._facts = fact_provider
        self._grounding = grounding
        self._langquality = langquality
        self._memory = memory_retriever
        self._suggester = memory_suggester
        self._store = store
        self._review = review_queue
        self._sink = trace_sink
        self._capture_content = capture_content
        self._budget = ContextBudget(settings, llm)

    async def run(self, request: TurnRequest) -> TurnResult:
        trace = TurnTrace(
            sink=self._sink,
            user_id=request.user_id,
            conversation_id=request.conversation_id,
            locale=request.locale,
            capture_content=self._capture_content,
        )
        trace.start()

        # -- 1. language / script detection -------------------------------
        detected = detect(request.text, request.locale)
        trace.span(
            Stage.LANGUAGE_DETECT,
            metadata={
                "detected_locale": detected.detected_locale,
                "script": detected.script.value,
                "matches_profile": detected.matches_profile,
                "confidence": detected.confidence,
            },
        )
        locale = detected.locale

        # -- 2. safety pre-check ------------------------------------------
        safety = await self._safety_pre.assess(request.text, locale)
        trace.span(
            Stage.SAFETY_PRE,
            status="flagged" if safety.level is not SafetyLevel.L1_CLEAR else "passed",
            metadata={
                "level": safety.level.name,
                "risk_class": safety.risk_class.value,
                "classifier_degraded": safety.degraded,
            },
        )
        if safety.level is SafetyLevel.L4_CRISIS:
            return await self._crisis_turn(request, trace, safety, locale)

        # -- 3. intent routing ---------------------------------------------
        decision = await self._router.route(request.text, locale, safety)
        trace.span(
            Stage.INTENT,
            metadata={
                "intent": decision.intent.value,
                "confidence": decision.confidence,
                "tools_granted": [tool.value for tool in decision.tools],
            },
        )

        # -- 4. required-data / confidence ---------------------------------
        sufficiency = required_data.assess(
            decision,
            request.profile,
            has_current_location=bool(request.place_label),
        )
        trace.span(
            Stage.REQUIRED_DATA,
            status="passed" if sufficiency.can_answer else "insufficient",
            metadata={
                "confidence": sufficiency.confidence.value,
                "missing": list(sufficiency.missing),
            },
        )
        if not sufficiency.can_answer:
            # §5.3: missing data → Tara asks, in-locale. Never a guess, and
            # never a generated sentence that might guess.
            return await self._template_turn(
                request,
                trace,
                safety,
                locale,
                intent=decision.intent,
                confidence=ConfidenceState.CANNOT_CALCULATE,
                message_key=_missing_key(sufficiency.missing),
                presence=PresenceState.THOUGHTFUL,
            )

        # -- 5 ∥ 6. memory retrieval ∥ fact tool-calls ----------------------
        memories, (snapshots, declines) = await asyncio.gather(
            self._retrieve_memories(request, locale),
            gather_facts(
                decision.tools,
                self._facts,
                FactContext(
                    user_id=request.user_id,
                    now=request.now,
                    locale=locale,
                    profile=request.profile,
                    place_label=request.place_label,
                    slots=decision.slots,
                ),
            ),
        )
        visible = memory_mod.apply_visibility_gates(memories, decision.intent, safety)
        trace.span(
            Stage.MEMORY_RETRIEVAL,
            metadata={"retrieved": len(memories), "after_gates": len(visible)},
        )
        trace.span(
            Stage.FACT_TOOLS,
            status="passed" if not declines else "partial",
            metadata={"fetched": len(snapshots), "declined": declines},
        )

        # -- 7. fact validation --------------------------------------------
        facts = validate(snapshots, request.now, notes=tuple(declines))
        confidence = required_data.downgrade_for_facts(sufficiency.confidence, facts)
        trace.span(
            Stage.FACT_VALIDATION,
            status="passed" if not facts.rejected else "partial",
            metadata={
                "accepted": len(facts.snapshots),
                "rejected": list(facts.rejected),
                "confidence": confidence.value,
            },
        )
        if decision.tools and not facts.snapshots and safety.astrology_allowed:
            # Tools were granted and none of them answered. Generating here
            # would hand the model an empty payload and a question about a
            # transit — the exact shape of a fabrication (§5.3).
            return await self._template_turn(
                request,
                trace,
                safety,
                locale,
                intent=decision.intent,
                confidence=ConfidenceState.CANNOT_CALCULATE,
                message_key=KEY_CANNOT_CALCULATE,
                presence=PresenceState.THOUGHTFUL,
            )

        # -- 8. response generation (+ 9, 10, 11 as its gate) ---------------
        plan = await self._budget.plan(
            history=request.history, summary=request.summary, locale=locale
        )
        outcome = await self._generate_validated(
            request, trace, safety, locale, decision.intent, confidence, facts, visible, plan
        )

        # -- 12. presence -----------------------------------------------------
        presence = _presence_for(safety, decision.intent, outcome.accepted)
        trace.span(Stage.PRESENCE, metadata={"state": presence.value})

        # -- 13. transcript store ---------------------------------------------
        # §9's order is "transcript store → memory-chip suggestion", and the
        # order is load-bearing: §6.4 gives a memory a source-message ref, so
        # the chip needs a message that already exists.
        message_id = await self._persist(
            request,
            locale=locale,
            reply=outcome.text,
            facts=facts if outcome.accepted else ValidatedFacts(),
            safety=safety,
            confidence=confidence,
            trace_id=trace.trace_id,
            intent=decision.intent,
        )
        trace.span(Stage.PERSIST, metadata={"message_id": message_id})

        # -- 14. memory-chip suggestion ---------------------------------------
        chips: tuple[MemoryChip, ...] = ()
        if outcome.accepted and self._settings.memory_chip_suggestions_enabled:
            chips = tuple(
                await self._suggester.suggest(
                    user_text=request.text,
                    reply_text=outcome.text,
                    locale=locale,
                    intent=decision.intent,
                )
            )
        trace.span(Stage.MEMORY_CHIP, metadata={"suggested": len(chips)})

        return TurnResult(
            text=outcome.text,
            locale=locale,
            confidence=confidence,
            safety=safety,
            intent=decision.intent,
            presence_state=presence,
            trace_id=trace.trace_id,
            fact_ids=facts.fact_ids if outcome.accepted else (),
            fact_snapshots=facts.snapshots if outcome.accepted else (),
            memory_chips=chips,
            message_key=None if outcome.accepted else KEY_FALLBACK,
            regenerations=outcome.regenerations,
            review_queued=outcome.review_queued,
            budget_notice_key=daily_cap_notice(self._settings, request.tokens_used_today),
            usage=outcome.usage,
            message_id=message_id,
        )

    async def _retrieve_memories(self, request: TurnRequest, locale: str):  # noqa: ANN202
        """Memory is context, not correctness. Losing it degrades the reply;
        it must not fail the turn — the facts side already works this way."""
        try:
            return await self._memory.retrieve(
                user_id=request.user_id,
                query=request.text,
                locale=locale,
                top_k=self._settings.memory_top_k,
            )
        except Exception:  # noqa: BLE001 — a retriever fault is not a 500
            logger.warning("memory retrieval failed — continuing without context")
            return ()

    # ----------------------------------------------------------------------
    # Generation + the three validators
    # ----------------------------------------------------------------------

    async def _generate_validated(
        self,
        request: TurnRequest,
        trace: TurnTrace,
        safety: SafetyAssessment,
        locale: str,
        intent: Intent,
        confidence: ConfidenceState,
        facts: ValidatedFacts,
        memories,  # noqa: ANN001 — Sequence[MemoryItem]
        plan,  # noqa: ANN001 — ContextPlan
    ) -> _Outcome:
        system = prompts.build_system(locale, safety)
        facts_block = prompts.render_facts(facts.snapshots)
        memory_block = memory_mod.render_for_prompt(memories)
        # §9: 0.2 for guidance composition, 0.7 ONLY for small talk.
        temperature = (
            self._settings.temperature_small_talk
            if required_data.is_small_talk(intent)
            else self._settings.temperature_guidance
        )

        usage = TokenUsage()
        correction: str | None = None
        attempts = self._settings.max_corrective_regenerations + 1

        for attempt in range(attempts):
            messages = prompts.build_messages(
                user_text=request.text,
                locale=locale,
                confidence=confidence,
                facts_block=facts_block,
                memory_block=memory_block,
                summary=plan.summary,
                history=plan.history,
                correction=correction,
            )
            try:
                response = await self._llm.complete(
                    LLMRequest(
                        task=LLMTask.CONVERSATION,
                        system=system.blocks,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=self._settings.max_output_tokens_turn,
                        label="generate",
                        cacheable_prefix_len=system.cacheable_prefix_len,
                    )
                )
            except LLMUnavailable:
                trace.span(Stage.GENERATION, status="failed", metadata={"reason": "unavailable"})
                # §8 calls a provider outage a degradation, not a safety event.
                # Filing it in §22.9's 24h-SLA queue would bury real L4 events
                # under provider flapping, so this rung serves the fallback
                # line WITHOUT queueing a human.
                return _Outcome(
                    text=localisation.resolve(KEY_FALLBACK, locale),
                    accepted=False,
                    regenerations=attempt,
                    usage=usage,
                    review_queued=False,
                    degraded=True,
                )

            usage = usage + TokenUsage(
                response.input_tokens,
                response.output_tokens,
                response.cache_read_tokens,
                response.cache_write_tokens,
            )
            trace.generation(
                Stage.GENERATION,
                model=response.model,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                cache_read_tokens=response.cache_read_tokens,
                cache_write_tokens=response.cache_write_tokens,
                status="truncated" if response.truncated else "passed",
                metadata={
                    "attempt": attempt,
                    "prompt_version": prompts.PROMPT_VERSION,
                    "applied": response.applied,
                    "truncated": response.truncated,
                },
                content=response.text,
            )

            failure: tuple[Stage, tuple[str, ...]] | None
            if response.truncated:
                # A reply cut off at §9's per-turn cap has lost whatever came
                # after the cut — usually its closing citation. Failing it here
                # spends the one regeneration on brevity rather than letting
                # the grounding validator blame the citations.
                failure = (
                    Stage.GENERATION,
                    ("reply hit the per-turn token cap and was cut off mid-sentence",),
                )
            else:
                failure = self._validate(trace, response.text, facts, locale)
            if failure is None:
                clean = self._grounding.check(response.text, facts, locale).clean_text
                return _Outcome(
                    text=clean, accepted=True, regenerations=attempt, usage=usage
                )

            stage, reasons = failure
            if attempt + 1 < attempts:
                correction = _correction_text(stage, reasons)
                continue

            outcome = await self._fallback(
                request, trace, safety, locale, stage, "; ".join(reasons)[:500], attempt
            )
            return _Outcome(
                text=outcome.text,
                accepted=False,
                regenerations=attempt,
                usage=usage,
                review_queued=True,
            )

        raise AssertionError("unreachable: the attempt loop always returns")

    def _validate(
        self, trace: TurnTrace, text: str, facts: ValidatedFacts, locale: str
    ) -> tuple[Stage, tuple[str, ...]] | None:
        """§9 stages 9, 10, 11 in order. First failure wins the regeneration."""
        grounding = self._grounding.check(text, facts, locale)
        trace.span(
            Stage.GROUNDING,
            status="passed" if grounding.ok else "failed",
            metadata={
                "cited": list(grounding.cited_fact_ids),
                "unknown_fact_ids": list(grounding.unknown_fact_ids),
                "uncited_claims": len(grounding.uncited_claims),
                "numeric_mismatches": list(grounding.numeric_mismatches),
            },
        )
        if not grounding.ok:
            return Stage.GROUNDING, grounding.reasons

        quality = self._langquality.check(grounding.clean_text, locale)
        trace.span(
            Stage.LANGUAGE_QUALITY,
            status="passed" if quality.ok else "failed",
            metadata={"failures": list(quality.failures)},
        )
        if not quality.ok:
            return Stage.LANGUAGE_QUALITY, quality.failures

        fear = self._fear_lint.check(grounding.clean_text, locale)
        leak = check_no_prompt_leak(grounding.clean_text)
        trace.span(
            Stage.SAFETY_POST,
            status="passed" if (fear.ok and leak.ok) else "failed",
            metadata={
                "fear_selling_hits": [hit.rule_id for hit in fear.hits],
                "prompt_leak": list(leak.matched),
            },
        )
        if not fear.ok:
            return Stage.SAFETY_POST, fear.reasons
        if not leak.ok:
            return Stage.SAFETY_POST, tuple(f"prompt fragment leaked: {m}" for m in leak.matched)
        return None

    # ----------------------------------------------------------------------
    # Terminal paths
    # ----------------------------------------------------------------------

    async def _fallback(
        self,
        request: TurnRequest,
        trace: TurnTrace,
        safety: SafetyAssessment,
        locale: str,
        stage: Stage,
        reason: str,
        attempt: int,
    ) -> _Outcome:
        """§9 / §2.4 rule 8: safe fallback line + human review queue."""
        await self._review.enqueue(
            ReviewEntry(
                stage=stage,
                reason=reason,
                trace_id=trace.trace_id,
                user_ref=pseudonymise(request.user_id),
                conversation_id=request.conversation_id,
                locale=locale,
                level=SafetyLevel.L5_HUMAN_REVIEW,
                created_at=request.now,
                assessment=safety,
            )
        )
        logger.warning(
            "turn fell back after validator failure",
            extra={"stage": stage.value, "trace_id": trace.trace_id},
        )
        return _Outcome(
            text=localisation.resolve(KEY_FALLBACK, locale),
            accepted=False,
            regenerations=attempt,
            usage=TokenUsage(),
            review_queued=True,
        )

    async def _crisis_turn(
        self,
        request: TurnRequest,
        trace: TurnTrace,
        safety: SafetyAssessment,
        locale: str,
    ) -> TurnResult:
        """§22.9: the L4 auto-response is instant and machine-delivered.

        No model call, no facts, no astrology — and the human review that
        follows is oversight, not the person's lifeline.
        """
        await self._review.enqueue(
            ReviewEntry(
                stage=Stage.SAFETY_PRE,
                reason=f"L4:{safety.risk_class.value}",
                trace_id=trace.trace_id,
                user_ref=pseudonymise(request.user_id),
                conversation_id=request.conversation_id,
                locale=locale,
                level=SafetyLevel.L4_CRISIS,
                created_at=request.now,
                assessment=safety,
            )
        )
        return await self._template_turn(
            request,
            trace,
            safety,
            locale,
            intent=Intent.EMOTIONAL_SUPPORT,
            confidence=ConfidenceState.CANNOT_CALCULATE,
            message_key=KEY_CRISIS,
            presence=PresenceState.SAFETY_STILL,
            review_queued=True,
        )

    async def _template_turn(
        self,
        request: TurnRequest,
        trace: TurnTrace,
        safety: SafetyAssessment,
        locale: str,
        *,
        intent: Intent,
        confidence: ConfidenceState,
        message_key: str,
        presence: PresenceState,
        review_queued: bool = False,
    ) -> TurnResult:
        """An authored, in-locale reply. Never generated, never cited."""
        text = localisation.resolve(message_key, locale)
        trace.span(Stage.GENERATION, status="templated", metadata={"message_key": message_key})
        trace.span(Stage.PRESENCE, metadata={"state": presence.value})
        message_id = await self._persist(
            request,
            locale=locale,
            reply=text,
            facts=ValidatedFacts(),
            safety=safety,
            confidence=confidence,
            trace_id=trace.trace_id,
            intent=intent,
        )
        return TurnResult(
            text=text,
            locale=locale,
            confidence=confidence,
            safety=safety,
            intent=intent,
            presence_state=presence,
            trace_id=trace.trace_id,
            message_key=message_key,
            review_queued=review_queued,
            budget_notice_key=daily_cap_notice(self._settings, request.tokens_used_today),
            message_id=message_id,
        )

    # ----------------------------------------------------------------------

    async def _persist(
        self,
        request: TurnRequest,
        *,
        locale: str,
        reply: str,
        facts: ValidatedFacts,
        safety: SafetyAssessment,
        confidence: ConfidenceState,
        trace_id: str,
        intent: Intent,
    ) -> str:
        await self._store.save_message(
            build_message(
                conversation_id=request.conversation_id,
                role="user",
                content=request.text,
                locale=locale,
                safety=safety,
                now=request.now,
            )
        )
        message_id = await self._store.save_message(
            build_message(
                conversation_id=request.conversation_id,
                role="assistant",
                content=reply,
                locale=locale,
                fact_snapshots=facts.snapshots,
                now=request.now,
            )
        )
        if facts.snapshots:
            # §30.4: every astrological claim is reachable to a Trust Sheet in
            # one tap, and the sheet reads this row.
            await self._store.save_guidance_log(
                build_guidance_log(
                    user_id=request.user_id,
                    local_date=request.now.date().isoformat(),
                    message_id=message_id,
                    fact_snapshots=facts.snapshots,
                    confidence=confidence,
                    why={
                        "intent": intent.value,
                        "trace_id": trace_id,
                        "sources": sorted({f.source.value for f in facts.snapshots}),
                        "notes": list(facts.notes),
                    },
                    now=request.now,
                )
            )
        return message_id


@dataclass(frozen=True)
class _Outcome:
    text: str
    accepted: bool
    regenerations: int
    usage: TokenUsage
    review_queued: bool = False
    #: The §8 ladder ran (provider outage), as distinct from a validator
    #: failure. Both serve the fallback line; only one queues a human.
    degraded: bool = False


def _correction_text(stage: Stage, reasons: tuple[str, ...]) -> str:
    """The single corrective instruction (§9). Names the rule, not the draft."""
    joined = "; ".join(reasons[:4])
    match stage:
        case Stage.GROUNDING:
            return (
                "Your previous reply broke the citation rule and was discarded: "
                f"{joined}. Use only the fact_ids in the <facts> block above, copied "
                "exactly, and state no number that is not in the fact you cite. If the "
                "facts do not support the answer, say so instead."
            )
        case Stage.LANGUAGE_QUALITY:
            return (
                f"Your previous reply failed the language check and was discarded: {joined}. "
                "Write it again in the required locale, script and register."
            )
        case _:
            return (
                f"Your previous reply failed the safety check and was discarded: {joined}. "
                "Write it again with no prediction of harm and no urgency."
            )


def _missing_key(missing: tuple[str, ...]) -> str:
    for field_name in ("birth_date", "birth_place", "current_location"):
        if field_name in missing:
            return _MISSING_KEYS[field_name]
    return KEY_CANNOT_CALCULATE


def _presence_for(safety: SafetyAssessment, intent: Intent, accepted: bool) -> PresenceState:
    """§4.3. Deterministic for now; §9's structured presence-state tag joins
    the voice/presence module, and this stays the floor under it."""
    if not safety.astrology_allowed:
        # State 11: "neutral, steady — used L2+; no smile, no astrology framing".
        # Every flagged risk class lands here, since the ladder only leaves
        # `astrology_allowed` true at L1 — where the risk class is NONE.
        return PresenceState.SAFETY_STILL
    if not accepted:
        return PresenceState.THOUGHTFUL
    if intent is Intent.GREETING_SMALLTALK:
        return PresenceState.WELCOME
    if intent is Intent.EMOTIONAL_SUPPORT:
        return PresenceState.CONCERN_KIND
    return PresenceState.CALM_GUIDANCE


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC)
