"""Chat-orchestration configuration (§9).

Everything a safety reviewer or an operator needs to tune lives here or in
`policy/*.json` — never inline in a stage. The fear-selling corpus and the L1
rule lexicon are per-locale data files precisely because §14 says "the
fear-selling lint corpus runs per-locale (fatalistic phrasing differs by
language — reviewed by native safety reviewers)": a reviewer edits JSON, not
Python.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

POLICY_DIR = Path(__file__).parent / "policy"
GLOSSARY_PATH = Path(__file__).resolve().parents[5] / "packages" / "i18n" / "glossary.json"


class ChatSettings(BaseSettings):
    """Env-overridable, prefix `CHAT_` except where the vendor names the key."""

        # populate_by_name: a `validation_alias` REPLACES the field name, so
        # `Settings(anthropic_api_key=...)` would silently produce None while
        # looking like it worked. Both spellings must bind.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="CHAT_",
        populate_by_name=True,
    )

    # --- model routing (§9) ----------------------------------------------
    # "primary Claude (latest Sonnet-class for conversations; Haiku-class for
    # classification/ranking polish) via a thin model-abstraction layer that
    # PINS VERSIONS and routes by task". These are those pins. The spec fixes
    # the tier, not the point release — bump the id here, never in a stage.
    conversation_model: str = "claude-sonnet-5"
    classification_model: str = "claude-haiku-4-5"
    #: §9's "fallback provider (secondary frontier model) behind the same
    #: interface". Unset means no fallback rung; §8 then degrades to the
    #: cached/templated path rather than silently answering worse.
    fallback_conversation_model: str | None = None

    anthropic_api_key: str | None = Field(
        default=None, validation_alias="ANTHROPIC_API_KEY"
    )
    llm_timeout_seconds: float = 30.0
    llm_max_retries: int = 2

    # --- generation parameters (§9) --------------------------------------
    # "Low-temperature (0.2) for guidance composition; 0.7 only for small
    # talk." Declared here and applied by the adapter wherever the pinned
    # model accepts a sampling parameter; see llm.py for what happens when it
    # does not.
    temperature_guidance: float = 0.2
    temperature_small_talk: float = 0.7
    temperature_classification: float = 0.0

    # --- token budgets (§9) ----------------------------------------------
    #: "rolling conversation summary (Haiku) keeps context <8K tokens"
    context_token_budget: int = 8_000
    #: Summarise once the kept history crosses this, before the budget bites.
    summary_trigger_tokens: int = 6_000
    #: Turns kept verbatim after a summary rolls; older ones become summary.
    history_keep_turns: int = 6
    #: "per-turn hard cap". Raised to 2048 after the M5 locale reproduction:
    #: Hinglish replies carry both scripts' worth of tokens and were being cut
    #: off mid-sentence, which cost the turn its §9 regeneration on brevity
    #: rather than on anything real.
    max_output_tokens_turn: int = 2_048
    max_output_tokens_classification: int = 512
    max_output_tokens_summary: int = 512
    #: "per-user daily soft cap with graceful in-locale notice" — a notice,
    #: never a refusal. Crossing it sets `budget_notice_key` on the result.
    daily_soft_cap_tokens: int = 120_000

    # --- safety thresholds (§9 L1 pre-check) ------------------------------
    #: A category at or above this becomes a flag → L2 constrained mode.
    safety_flag_threshold: float = 0.5
    #: At or above this, an acute-crisis signal goes straight to L4.
    safety_crisis_threshold: float = 0.8
    #: The rule lexicon always runs; the classifier is the second opinion.
    #: With it off (or down) rules alone still raise L4 — fail-safe, not
    #: fail-open.
    safety_classifier_enabled: bool = True

    # --- validators -------------------------------------------------------
    #: §9 fixes this: "fail → one corrective regeneration → fail → safe
    #: fallback line + human review queue". Validated below; it is not a knob.
    max_corrective_regenerations: int = 1

    # --- memory (§32.5) ----------------------------------------------------
    memory_top_k: int = 6
    memory_chip_suggestions_enabled: bool = False

    # --- tracing (§9 cost controls) ---------------------------------------
    langfuse_enabled: bool = False
    langfuse_host: str | None = None
    langfuse_public_key: str | None = None
    #: §13: message content, birth data and tokens can structurally never
    #: appear in application logs. Turning this on is a dev-only affordance
    #: and the tracer refuses it outside dev.
    trace_capture_content: bool = False

    @field_validator("max_corrective_regenerations")
    @classmethod
    def _one_regeneration_only(cls, v: int) -> int:
        if v != 1:
            raise ValueError(
                "§9 fixes the corrective regeneration at exactly one — "
                "changing it needs a §31.3 change-control entry, not an env var"
            )
        return v


@cache
def _load(name: str) -> dict[str, Any]:
    return json.loads((POLICY_DIR / name).read_text(encoding="utf-8"))


def safety_rules() -> dict[str, Any]:
    """L1 rule lexicon, per locale (§9)."""
    return _load("safety_rules.json")


def fear_selling_corpus() -> dict[str, Any]:
    """Post-check lint corpus, per locale (§9, §14)."""
    return _load("fear_selling.json")


def claim_terms() -> dict[str, Any]:
    """Per-locale astrology vocabulary the grounding validator gates on."""
    return _load("claim_terms.json")


def glossary_terms(locale: str = "en") -> tuple[tuple[str, tuple[str, ...]], ...]:
    """(term, forbidden renderings) from packages/i18n/glossary.json (§2.4).

    Read from the shared package rather than copied, so a glossary edit
    reaches the language-quality validator without a second review. English
    renderings are always included: an English gloss standing in for a native
    term is the violation regardless of the reply's locale.
    """
    path = GLOSSARY_PATH
    if not path.exists():  # deployed images ship the service, not the monorepo
        return (("Tara", ()), ("Sitara", ()))
    data = json.loads(path.read_text(encoding="utf-8"))
    rows: list[tuple[str, tuple[str, ...]]] = []
    for term in data.get("terms", []):
        blocked = term.get("forbidden_renderings", {})
        renderings = {*blocked.get(locale, ()), *blocked.get("en", ())}
        rows.append((term["term"], tuple(sorted(renderings))))
    return tuple(rows)


def glossary_review_status() -> str:
    if not GLOSSARY_PATH.exists():
        return "missing — glossary.json not found"
    data = json.loads(GLOSSARY_PATH.read_text(encoding="utf-8"))
    return data.get("review_status", "missing — no review_status field")
