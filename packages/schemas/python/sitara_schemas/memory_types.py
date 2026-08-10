"""GENERATED FILE — do not edit. Source: packages/schemas/src/*.json (run scripts/generate.py).

SPEC §32.4 — the eleven memory types.

The closed set of IDs only. The RULES attached to each type — consent,
visibility gates, decay half-lives — belong to the memory module (§6.3)
and stay in `sitara_api.memory.taxonomy`, which imports its enum from
here rather than declaring a second one.
"""

from enum import StrEnum


class MemoryType(StrEnum):
    """SPEC §32.4 — the eleven memory types. CLOSED SET. §32.4 ends 'Vault filters use exactly these 11 labels, localized', and until M8-P10 two different elevens were in the repo: `sitara_api.memory.taxonomy.MemoryType` had §32.4's (person, significant_event, date_anniversary, …) and `packages/i18n` had an invented parallel set (life_fact, concern, belief_practice, conversation_thread, …) that seven of eleven labels disagreed with. Nothing rendered a typed memory yet, so nothing failed. S18's memory chip is the first thing that does. `taxonomy.py` still OWNS the rules — consent, gates, decay half-lives are §6.3 the memory module's business and stay there; this file is only the closed set of IDS, so the catalogs and the vault can be checked against it mechanically. `dynamic-keys.json` reads it through `valuesFrom`."""

    PERSON = "person"
    SIGNIFICANT_EVENT = "significant_event"
    DATE_ANNIVERSARY = "date_anniversary"
    PREFERENCE = "preference"
    GOAL_INTENTION = "goal_intention"
    DECISION_CONTEXT = "decision_context"
    MOOD_PATTERN = "mood_pattern"
    HEALTH_ADJACENT = "health_adjacent"
    WORK_FINANCE = "work_finance"
    SPIRITUAL_PRACTICE = "spiritual_practice"
    PRONUNCIATION_IDENTITY = "pronunciation_identity"


#: §32.4's numbering, so the vault renders 1–11 as the spec numbers them.
MEMORY_TYPE_ORDER: tuple[MemoryType, ...] = (
    MemoryType.PERSON,
    MemoryType.SIGNIFICANT_EVENT,
    MemoryType.DATE_ANNIVERSARY,
    MemoryType.PREFERENCE,
    MemoryType.GOAL_INTENTION,
    MemoryType.DECISION_CONTEXT,
    MemoryType.MOOD_PATTERN,
    MemoryType.HEALTH_ADJACENT,
    MemoryType.WORK_FINANCE,
    MemoryType.SPIRITUAL_PRACTICE,
    MemoryType.PRONUNCIATION_IDENTITY,
)
