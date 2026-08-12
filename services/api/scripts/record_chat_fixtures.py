#!/usr/bin/env python3
"""Record §25.4's chat turns from the real §9 pipeline into committed JSON.

    uv run python scripts/record_chat_fixtures.py

Output: `apps/web/tests/__fixtures__/chat/<scenario>.<locale>.json`, replayed by
`apps/web/scripts/stub-realtime.mjs` over a real WebSocket.

**Why record rather than author** — the same reason `record_today_fixtures.py`
gives, and one more that is specific to chat.

The general reason: the web suite runs without Python, Mongo or a model key, so
the tempting alternative is to hand-write the turns in the stub. Every §24.8
baseline would then be a picture of a reply nobody's pipeline produced, and the
first real regression in grounding, safety or composition would leave all of
them green.

The specific one: a chat turn carries CITATION SPANS. `span_start`/`span_end`
index into the turn's own text and are computed by the grounding validator from
where it found the `[[fact:…]]` markers. Hand-written spans would be numbers
someone counted by eye — they would render an underline, they would look
plausible in a screenshot, and they would not be the spans the validator
produces. The one defect the S18 baselines exist to catch is an underline that
covers the wrong words, and authored fixtures cannot catch it by construction.

**The model is scripted, the pipeline is not.** Nothing here stubs a validator.
The scripted replies are what a model returns; grounding, language-quality,
the fear lint, the safety ladder and the presenter all run for real, which is
why the `fabricated` and `fear_selling` scenarios come back as the fallback
line rather than as what the model said.

Re-record after any change to the pipeline, the presenter or the templates. The
diff is the review artefact.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "apps" / "web" / "tests" / "__fixtures__" / "chat"

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sitara_schemas.facts import Graha  # noqa: E402

from sitara_api.chat_orchestration.presenter import present_turn  # noqa: E402
from sitara_api.chat_orchestration.types import (  # noqa: E402
    FactTool,
    TurnRequest,
)
from tests.chat.conftest import (  # noqa: E402
    CONVERSATION_ID,
    NOW,
    SATURN_FACT_ID,
    USER_ID,
    VENUS_FACT_ID,
    ScriptedSuggester,
    build_env,
    transit_house_fact,
)

LOCALES = ("en", "hi", "hi-Latn")

#: What the model returns, per scenario and locale. The PIPELINE is real; only
#: the model is scripted, so a reply that breaks a rule is rejected here
#: exactly as it would be in production.
REPLIES: dict[str, dict[str, str]] = {
    "grounded": {
        "en": (
            f"Saturn is moving through your 10th house today [[{SATURN_FACT_ID}]]. "
            "Take the slow route with work decisions — nothing here needs deciding by lunch."
        ),
        "hi": (
            f"आज शनि आपके 10वें भाव से गुज़र रहे हैं [[{SATURN_FACT_ID}]]। "
            "काम के फ़ैसलों में धीरज रखें।"
        ),
        "hi-Latn": (
            f"Aaj Shani aapke 10ve bhaav se guzar rahe hain [[{SATURN_FACT_ID}]]. "
            "Kaam ke faislon mein dheeraj rakhein."
        ),
    },
    #: Two claims, two underlines — the case that catches a span scan collapsing
    #: both citations onto the first occurrence.
    "two_claims": {
        "en": (
            f"Saturn is in your 10th house today [[{SATURN_FACT_ID}]]. "
            f"Venus is in your 5th house today [[{VENUS_FACT_ID}]]. "
            "Work asks for patience; the evening does not."
        ),
        "hi": (
            f"आज शनि आपके 10वें भाव में हैं [[{SATURN_FACT_ID}]]। "
            f"आज शुक्र आपके 5वें भाव में हैं [[{VENUS_FACT_ID}]]। "
            "काम धीरज माँगता है, शाम नहीं।"
        ),
        "hi-Latn": (
            f"Aaj Shani aapke 10ve bhaav mein hain [[{SATURN_FACT_ID}]]. "
            f"Aaj Shukra aapke 5ve bhaav mein hain [[{VENUS_FACT_ID}]]. "
            "Kaam dheeraj maangta hai, shaam nahi."
        ),
    },
    #: A claimless reply — small talk. No citations, so no underline and no
    #: ConfidenceChip: a bubble with nothing to explain offers no explanation.
    "claimless": {
        "en": "I'm here. Tell me what's on your mind and we'll take it from there.",
        "hi": "मैं यहीं हूँ। बताइए मन में क्या है, वहीं से शुरू करते हैं।",
        "hi-Latn": "Main yahin hoon. Bataiye mann mein kya hai, wahin se shuru karte hain.",
    },
    #: The model fabricates, twice. §9 allows one corrective regeneration and
    #: then serves the safe fallback line — so what is RECORDED here is the
    #: fallback, which is the whole point of the scenario.
    "fabricated": {
        "en": (
            "Jupiter is crossing your 7th house this week, so marriage talks "
            f"will go well [[{VENUS_FACT_ID}]]."
        ),
        "hi": (
            f"इस हफ़्ते गुरु आपके 7वें भाव से गुज़र रहे हैं [[{VENUS_FACT_ID}]]।"
        ),
        "hi-Latn": (
            f"Is hafte Guru aapke 7ve bhaav se guzar rahe hain [[{VENUS_FACT_ID}]]."
        ),
    },
}

#: Scenarios whose reply is scripted twice, because the first is rejected and
#: §9 spends its single regeneration before falling back.
REJECTED = {"fabricated"}

#: §32.4's consent chip, in two shapes that behave differently.
#:
#: The extractor's OUTPUT is scripted (it is a structured model output, §9);
#: `memory.chip_from` is not — so `requires_reconfirmation` is set by the real
#: §32.4 rule ("types 7–9 always re-confirm wording before save") rather than
#: by a fixture asserting it. Type 1 is a plain offer; type 7 is the one the UI
#: must let the user re-word before it is stored.
CHIPS: dict[str, dict[str, str]] = {
    "memory_offer": {"type": "person", "content": "Your sister Meera lives in Pune"},
    "memory_reconfirm": {
        "type": "mood_pattern",
        "content": "Mondays weigh on you more than the rest of the week",
    },
}

#: The L4 path never reaches the model at all (§22.9), so it is driven by the
#: USER's text rather than by a scripted reply.
CRISIS_TEXT = {
    "en": "I want to kill myself",
    "hi": "मैं अपनी जान लेना चाहता हूँ",
    "hi-Latn": "Main apni jaan lena chahta hoon",
}


async def record() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    written = 0

    for scenario, by_locale in REPLIES.items():
        for locale, reply in by_locale.items():
            env = build_env(
                facts_by_tool={
                    FactTool.TRANSITS: (
                        transit_house_fact(Graha.SATURN, 10, SATURN_FACT_ID),
                        transit_house_fact(Graha.VENUS, 5, VENUS_FACT_ID),
                    )
                }
            )
            env.llm.script("generate", *([reply, reply] if scenario in REJECTED else [reply]))
            result = await env.pipeline.run(
                TurnRequest(
                    user_id=USER_ID,
                    conversation_id=CONVERSATION_ID,
                    text="what is Saturn doing?",
                    locale=locale,
                    now=NOW,
                    profile=env.profile,
                )
            )
            _write(scenario, locale, present_turn(result))
            written += 1

    for scenario, raw in CHIPS.items():
        for locale in LOCALES:
            env = build_env(memory_suggester=ScriptedSuggester(raw))
            env.llm.script("generate", REPLIES["grounded"][locale])
            result = await env.pipeline.run(
                TurnRequest(
                    user_id=USER_ID,
                    conversation_id=CONVERSATION_ID,
                    text="what is Saturn doing?",
                    locale=locale,
                    now=NOW,
                    profile=env.profile,
                )
            )
            _write(scenario, locale, present_turn(result))
            written += 1

    for locale, text in CRISIS_TEXT.items():
        env = build_env()
        result = await env.pipeline.run(
            TurnRequest(
                user_id=USER_ID,
                conversation_id=CONVERSATION_ID,
                text=text,
                locale=locale,
                now=NOW,
                profile=env.profile,
            )
        )
        _write("crisis", locale, present_turn(result))
        written += 1

    return written


def _write(scenario: str, locale: str, turn: object) -> None:
    path = OUT / f"{scenario}.{locale}.json"
    payload = turn.model_dump(mode="json")  # type: ignore[attr-defined]
    # The recorded turns feed a stub that must not depend on a clock; the ids
    # the pipeline minted are real ObjectIds and are kept as-is.
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main() -> None:
    count = asyncio.run(record())
    print(f"recorded {count} chat turns → {OUT.relative_to(REPO)}")
    print("re-run after any pipeline, presenter or template change")


if __name__ == "__main__":
    main()
