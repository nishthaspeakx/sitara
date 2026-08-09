"""LLM polish for the morning brief (§7.1), and the gate behind it.

    "template composition + LLM polish (batched, low-temperature,
    prompt-cached) → grounding validation"

**Batched** means one call per BRIEF, not one per module. Seventeen calls where
one would do is seventeen stable prefixes to pay for and seventeen chances for
a module to drift out of step with its neighbours' tone. The modules go up
together, numbered, and come back numbered.

**Prompt-cached** is why the system blocks are ordered the way they are. Persona
→ citation contract → locale style guide, most stable first, and the cache
breakpoint sits after the last block that is stable ACROSS USERS. Everything
per-brief — the modules, the facts, the density — rides in the user message,
below the breakpoint. The whole IST-07:00 band shares one prefix, which is the
only reason §7.1 can call the Claude call "the only per-user marginal cost".

**Low-temperature** is declared, not sent blindly: §37 (CC-004) made the control
capability-relative, and `llm.py` applies the declared profile where the pinned
model accepts one and records `temperature_declared` where it does not. This
module declares §9's guidance value and otherwise stays out of it — a stage
naming a model or a sampling value is exactly what §9's adapter exists to
prevent.

**Grounding validation** is the gate, and it is the same validator the chat
pipeline uses. That is deliberate: one definition of "cited" in the service. A
polished module that loses its citation, invents a fact-ID or changes a number
is discarded and the brief keeps the composed text, which was true before the
model touched it.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass

from sitara_api.chat_orchestration.config import ChatSettings
from sitara_api.chat_orchestration.grounding import CITATION_RE, GroundingValidator
from sitara_api.chat_orchestration.llm import (
    LLMClient,
    LLMRequest,
    LLMTask,
    LLMUnavailable,
)
from sitara_api.daily_guidance.types import ComposedModule, Density

logger = logging.getLogger(__name__)

#: Bump on any edit below the fold — the cached prefix is keyed on its own
#: content, so a silent edit means a silent cache miss for every user at once.
BRIEF_PROMPT_VERSION = "brief-polish-v1"

_PERSONA = """You are polishing Tara's morning brief.

Tara is warm, plain-spoken and never dramatic. She sounds like a person who
knows this reader, not like a horoscope column. She never predicts death,
divorce, illness or ruin, never manufactures urgency, and never tells anyone
that something bad will happen if they do not act.
"""

_CITATION_CONTRACT = """You are rewriting sentences that are ALREADY TRUE.

Every sentence you receive ends with one or more citation markers of the form
[[fact:...]]. These rules are absolute:

1. Keep every marker, unchanged, on the sentence it arrived on.
2. Never add a marker that was not given to you.
3. Never change, round or add a number, a time or a house position. If the
   sentence says 07:12, your version says 07:12.
4. Never add an astrological claim that was not in the sentence you were given.
   You may change the words. You may not change what is asserted.
5. Return one polished sentence per input sentence, in the same order.

If you cannot polish a sentence without breaking a rule, return it unchanged.
"""

_STYLE_GUIDE = {
    "en": (
        "Write in English. Short sentences. No jargon the reader did not ask "
        "for. Never explain a Sanskrit term unless the input explained it."
    ),
    "hi": (
        "देवनागरी हिंदी में लिखें। छोटे वाक्य। अंग्रेज़ी शब्दों से बचें, "
        "पर पारंपरिक शब्द (तिथि, नक्षत्र, पक्ष) वैसे ही रखें।"
    ),
    "hi-Latn": (
        "Hinglish mein likhein — Latin script, natural spoken Hindi. English "
        "loanwords theek hain jahan log wahi bolte hain. Traditional terms "
        "(tithi, nakshatra, paksha) waise hi rakhein."
    ),
}

#: §28.2's density modes reach the model as a length instruction only. They
#: MUST NOT reach it as a fact instruction — the ranking engine already decided
#: what the reader sees, and a model asked to "add detail" for a HIGH user
#: would add it from somewhere.
_DENSITY_NOTE = {
    Density.LOW: "Keep each line very short. Plain language, no tradition terms explained.",
    Density.MED: "Keep each line short and warm.",
    Density.HIGH: "You may keep tradition terms as they are; this reader knows them.",
}

_SCHEMA = {
    "type": "object",
    "properties": {
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "text": {"type": "string"},
                },
                "required": ["index", "text"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["lines"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class PolishReport:
    """What polish achieved, per brief. Logged; never guessed at afterwards."""

    attempted: int = 0
    accepted: int = 0
    rejected: int = 0
    regenerated: bool = False
    unavailable: bool = False
    reasons: tuple[str, ...] = ()

    @property
    def all_rejected(self) -> bool:
        """Every line came back and every line failed grounding.

        This is the condition diagram 5 routes to the §7.1 degrade, and it is
        deliberately narrower than "accepted == 0": a provider outage also
        accepts nothing, and an outage is not a grounding failure. §8 degrades
        an outage gracefully — the composed text is already verified — while a
        model that cannot stop rewriting the facts is the case the degrade was
        written for.
        """
        return self.attempted > 0 and self.accepted == 0 and not self.unavailable


class BriefPolisher:
    """§7.1's polish step, with §9's exactly-one regeneration.

    §9 fixes the corrective-regeneration count at one for a chat turn, and the
    brief inherits it rather than inventing a second policy: fail → one
    corrective regeneration → fail → the engine-composed text stands. The brief
    does NOT queue a human review row for a grounding failure the way a chat
    turn does — nothing was served to anyone, the composed text is already
    verified, and §22.9's 24-hour queue is for people in difficulty, not for
    prose that came back slightly wrong at 05:40.
    """

    def __init__(
        self,
        llm: LLMClient,
        *,
        grounding: GroundingValidator | None = None,
        settings: ChatSettings | None = None,
    ) -> None:
        self._llm = llm
        self._grounding = grounding or GroundingValidator()
        self._settings = settings or ChatSettings()

    def _system_blocks(self, locale: str) -> tuple[tuple[str, ...], int]:
        """(blocks, cacheable prefix length).

        The style guide is the last block that is stable across users at one
        locale, so the breakpoint sits after it — three blocks, all cached. The
        density note is deliberately NOT a system block: it varies per user and
        would turn every brief into a cache write.
        """
        style = _STYLE_GUIDE.get(locale, _STYLE_GUIDE["en"])
        return (_PERSONA, _CITATION_CONTRACT, style), 3

    async def polish(
        self, modules: Sequence[ComposedModule], locale: str, density: Density
    ) -> tuple[list[ComposedModule], PolishReport]:
        """Polish a whole brief in one call, gate each line, return both."""
        if not modules:
            return [], PolishReport()

        system, prefix_len = self._system_blocks(locale)
        payload = {
            "density_note": _DENSITY_NOTE[density],
            "lines": [
                {"index": i, "text": module.text} for i, module in enumerate(modules)
            ],
        }
        request = LLMRequest(
            task=LLMTask.CONVERSATION,
            system=system,
            messages=({"role": "user", "content": json.dumps(payload, ensure_ascii=False)},),
            # §9's guidance value, declared. Whether it is SENT is the adapter's
            # decision under §37 — this stage never asks.
            temperature=self._settings.temperature_guidance,
            max_tokens=self._settings.max_output_tokens_turn,
            schema=_SCHEMA,
            label="brief.polish",
            cacheable_prefix_len=prefix_len,
        )

        try:
            response = await self._llm.complete(request)
        except LLMUnavailable:
            logger.warning("brief polish unavailable — composed text stands (§8)")
            return list(modules), PolishReport(
                attempted=len(modules), unavailable=True, reasons=("llm_unavailable",)
            )

        accepted, rejected, reasons = self._gate(modules, response.parsed, locale)

        regenerated = False
        if rejected and self._settings.max_corrective_regenerations:
            regenerated = True
            retry = LLMRequest(
                task=LLMTask.CONVERSATION,
                system=system,
                messages=(
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                    {"role": "assistant", "content": response.text},
                    {
                        "role": "user",
                        "content": (
                            "Some lines broke the rules: "
                            + "; ".join(reasons[:6])
                            + ". Return every line again, obeying rules 1-5 exactly. "
                            "Returning an input sentence unchanged is always allowed."
                        ),
                    },
                ),
                temperature=self._settings.temperature_guidance,
                max_tokens=self._settings.max_output_tokens_turn,
                schema=_SCHEMA,
                label="brief.polish.corrective",
                cacheable_prefix_len=prefix_len,
            )
            try:
                second = await self._llm.complete(retry)
            except LLMUnavailable:
                second = None
            if second is not None:
                accepted, rejected, reasons = self._gate(modules, second.parsed, locale)

        # `accepted` is keyed by input index and starts as a copy of the input,
        # so a rejected line is still present — carrying its COMPOSED text.
        # That is the point: a line the model spoiled falls back to the engine's
        # own sentence, which was true before polish ran.
        polished = [accepted[i] for i in sorted(accepted)]
        return polished, PolishReport(
            attempted=len(modules),
            accepted=sum(1 for m in polished if m.polished_text),
            rejected=len(rejected),
            regenerated=regenerated,
            reasons=tuple(reasons),
        )

    def _gate(
        self,
        modules: Sequence[ComposedModule],
        parsed: dict | None,
        locale: str,
    ) -> tuple[dict[int, ComposedModule], list[int], list[str]]:
        """Grounding-check each polished line against ITS OWN module's facts.

        Per-module rather than per-brief on purpose: checking a line against the
        union of the brief's facts would let a polished caution window quote a
        time from the favourable window and pass. The citation says which fact
        the sentence stands on, and that is the fact the number must come from.
        """
        by_index = {i: module for i, module in enumerate(modules)}
        out: dict[int, ComposedModule] = dict(by_index)
        rejected: list[int] = []
        reasons: list[str] = []

        lines = (parsed or {}).get("lines") or []
        seen: set[int] = set()
        for line in lines:
            index = line.get("index")
            text = (line.get("text") or "").strip()
            module = by_index.get(index) if isinstance(index, int) else None
            if module is None or not text:
                continue
            seen.add(index)

            # A structural check the chat pipeline cannot make, and the brief
            # can. `GroundingValidator` decides "is this a claim?" from
            # vocabulary, which is the only thing available for free-form
            # conversation — and it means a sentence naming no astrological
            # term passes uncited even when it carries real times. "A good
            # window opens between 11:48 and 12:36" is exactly that shape, and
            # in a template it is not an edge case, it is every morning.
            #
            # Here we already KNOW the sentence stands on facts, because the
            # composer put them there. So the requirement is structural: a
            # module composed from snapshots must come back citing at least one
            # of them. The vocabulary test below still runs, and still catches
            # the claims this one cannot see.
            if module.snapshots:
                cited = set(CITATION_RE.findall(text))
                if not cited & set(module.fact_ids):
                    rejected.append(index)
                    reasons.append(
                        f"line {index} lost the citation for "
                        f"{module.module.value} — composed from facts, returned without one"
                    )
                    continue

            verdict = self._grounding.check(text, module.snapshots, locale)
            if not verdict.ok:
                rejected.append(index)
                reasons.extend(verdict.reasons[:2])
                continue
            # `clean_text` is the citation-stripped rendering the user reads;
            # the markers stay out of the stored text exactly as in chat (§30.4).
            out[index] = ComposedModule(
                module=module.module,
                text=module.text,
                polished_text=verdict.clean_text,
                snapshots=module.snapshots,
                template_id=module.template_id,
            )

        for index in by_index:
            if index not in seen:
                rejected.append(index)
                reasons.append(f"line {index} missing from the polished response")

        return out, rejected, reasons
