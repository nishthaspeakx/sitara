"""§32.4's taxonomy, asserted against the spec text rather than the code."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from sitara_api.memory.taxonomy import (
    ALWAYS_AVAILABLE,
    CONTEXT_GATED,
    MEMORY_TYPE_ORDER,
    NEVER_DECAYS,
    NEVER_IN_CASUAL,
    RECONFIRM_WORDING,
    MemoryType,
    is_medical_content,
)

SPEC = Path(__file__).resolve().parents[4] / "docs" / "spec" / "SPEC.md"


def spec_324() -> str:
    text = SPEC.read_text(encoding="utf-8")
    match = re.search(r"\*\*32\.4 The 11 memory types.*?(?=\n\n)", text, re.DOTALL)
    assert match, "§32.4 not found in SPEC.md"
    return match.group(0)


class TestAgainstTheSpecText:
    """§32.4 is parsed out of the spec, the way tests/db does for §6.4 — the
    taxonomy and the document that mandates it cannot drift apart silently."""

    def test_there_are_exactly_eleven(self) -> None:
        assert len(MEMORY_TYPE_ORDER) == 11
        assert len(set(MEMORY_TYPE_ORDER)) == 11
        assert "The 11 memory types" in spec_324()

    def test_every_type_name_appears_in_the_spec_paragraph(self) -> None:
        """A type the spec does not name is a type we invented."""
        paragraph = spec_324().lower()
        expected_words = {
            MemoryType.PERSON: "person",
            MemoryType.SIGNIFICANT_EVENT: "significant event",
            MemoryType.DATE_ANNIVERSARY: "date/anniversary",
            MemoryType.PREFERENCE: "preference",
            MemoryType.GOAL_INTENTION: "goal/intention",
            MemoryType.DECISION_CONTEXT: "decision-context",
            MemoryType.MOOD_PATTERN: "mood/emotional pattern",
            MemoryType.HEALTH_ADJACENT: "health-adjacent",
            MemoryType.WORK_FINANCE: "work/finance context",
            MemoryType.SPIRITUAL_PRACTICE: "spiritual practice",
            MemoryType.PRONUNCIATION_IDENTITY: "pronunciation/identity",
        }
        assert set(expected_words) == set(MemoryType)
        for memory_type, phrase in expected_words.items():
            assert phrase in paragraph, f"{memory_type} — §32.4 does not say {phrase!r}"

    def test_the_spec_still_says_types_7_to_9_reconfirm(self) -> None:
        assert "types 7–9 always re-confirm wording before save" in spec_324()
        assert RECONFIRM_WORDING == {
            MemoryType.MOOD_PATTERN,  # 7
            MemoryType.HEALTH_ADJACENT,  # 8
            MemoryType.WORK_FINANCE,  # 9
        }

    def test_the_spec_still_says_8_is_never_casual_and_11_always(self) -> None:
        paragraph = spec_324()
        assert "8 never in celebratory/casual turns" in paragraph
        assert "11 always available" in paragraph
        assert NEVER_IN_CASUAL == {MemoryType.HEALTH_ADJACENT}
        assert ALWAYS_AVAILABLE == {MemoryType.PRONUNCIATION_IDENTITY}

    def test_the_spec_still_says_1_3_11_never_decay(self) -> None:
        assert "1,3,11 never auto-decay" in spec_324()
        assert NEVER_DECAYS == {
            MemoryType.PERSON,
            MemoryType.DATE_ANNIVERSARY,
            MemoryType.PRONUNCIATION_IDENTITY,
        }

    def test_context_gating_covers_exactly_types_7_to_9(self) -> None:
        assert "Visibility gates: 7–9 retrieved only in matching" in spec_324()
        assert CONTEXT_GATED == RECONFIRM_WORDING


class TestMedicalDecline:
    """§32.4: health-adjacent is "non-medical framing; NEVER
    symptoms/diagnoses — those are declined at classification"."""

    @pytest.mark.parametrize(
        "content",
        [
            "I was diagnosed with diabetes",
            "my symptoms got worse this week",
            "the doctor prescribed a new medication",
            "my blood pressure is high",
            "मुझे यह निदान मिला है",
        ],
    )
    def test_medical_content_is_recognised(self, content: str) -> None:
        assert is_medical_content(content)

    @pytest.mark.parametrize(
        "content",
        [
            "I walk every morning before work",
            "I have been sleeping better since last week",
            "I fast on Tuesdays",
            "I cut down on sugary drinks",
        ],
    )
    def test_wellbeing_framing_is_allowed(self, content: str) -> None:
        assert not is_medical_content(content)


def test_the_taxonomy_has_exactly_one_home() -> None:
    """chat_orchestration re-exports rather than redeclaring — two copies of
    an 11-member closed set is how a twelfth appears."""
    from sitara_api.chat_orchestration.types import MemoryType as ReExported

    assert ReExported is MemoryType
