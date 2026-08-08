"""Token budgets and the rolling conversation summary (§9).

§9: "rolling conversation summary (Haiku) keeps context <8K tokens; per-turn
hard cap; per-user daily soft cap with graceful in-locale notice."

Three distinct controls, and the difference between them matters:
* the ROLLING SUMMARY keeps the context small and is invisible to the user;
* the PER-TURN CAP is `max_tokens` on the request — a hard ceiling;
* the DAILY SOFT CAP is a notice, never a refusal. §29.2 forbids dark
  patterns, and cutting someone off mid-conversation to protect a cost line
  would be one. The turn completes; the notice explains.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from sitara_api.chat_orchestration.config import ChatSettings
from sitara_api.chat_orchestration.llm import (
    LLMClient,
    LLMRequest,
    LLMTask,
    LLMUnavailable,
    estimate_tokens,
)
from sitara_api.chat_orchestration.prompts import SUMMARY_SYSTEM

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ContextPlan:
    """What this turn will actually send."""

    history: tuple[dict[str, str], ...]
    summary: str | None
    #: True when a fresh summary was produced and should be persisted.
    summary_refreshed: bool = False
    estimated_tokens: int = 0


class ContextBudget:
    def __init__(self, settings: ChatSettings, llm: LLMClient) -> None:
        self._settings = settings
        self._llm = llm

    async def plan(
        self,
        *,
        history: Sequence[dict[str, str]],
        summary: str | None,
        locale: str,
    ) -> ContextPlan:
        keep = self._settings.history_keep_turns
        recent = tuple(history[-keep:])
        older = tuple(history[:-keep]) if len(history) > keep else ()

        estimated = _estimate(recent) + estimate_tokens(summary or "")
        if not older and estimated < self._settings.summary_trigger_tokens:
            return ContextPlan(history=recent, summary=summary, estimated_tokens=estimated)

        rolled = await self._summarise(older, summary, locale)
        if rolled is None:
            # Summarisation failed. Truncating history is the honest
            # degradation: a shorter memory beats a blown context window, and
            # the facts for this turn are fetched fresh regardless.
            logger.warning("rolling summary unavailable — sending recent turns only")
            return ContextPlan(history=recent, summary=summary, estimated_tokens=estimated)

        return ContextPlan(
            history=recent,
            summary=rolled,
            summary_refreshed=True,
            estimated_tokens=_estimate(recent) + estimate_tokens(rolled),
        )

    async def _summarise(
        self, older: Sequence[dict[str, str]], previous: str | None, locale: str
    ) -> str | None:
        if not older and not previous:
            return None
        transcript = "\n".join(
            f"{turn.get('role', 'user')}: {turn.get('content', '')}" for turn in older
        )
        prior = f"<previous_summary>\n{previous}\n</previous_summary>\n\n" if previous else ""
        try:
            response = await self._llm.complete(
                LLMRequest(
                    task=LLMTask.SUMMARY,
                    system=(SUMMARY_SYSTEM,),
                    messages=(
                        {
                            "role": "user",
                            "content": (
                                f"{prior}<locale>{locale}</locale>\n"
                                f"<transcript>\n{transcript}\n</transcript>"
                            ),
                        },
                    ),
                    temperature=self._settings.temperature_classification,
                    max_tokens=self._settings.max_output_tokens_summary,
                    label="summary.rolling",
                )
            )
        except LLMUnavailable:
            return None
        return response.text.strip() or None


def daily_cap_notice(settings: ChatSettings, tokens_used_today: int) -> str | None:
    """§9's soft cap. Returns an i18n key, never a block."""
    if tokens_used_today >= settings.daily_soft_cap_tokens:
        return "chat.budget.daily_soft_cap"
    return None


def _estimate(history: Sequence[dict[str, str]]) -> int:
    return sum(estimate_tokens(turn.get("content", "")) for turn in history)
