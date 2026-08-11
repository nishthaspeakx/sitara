"""The 11 memory types and the three rule sets attached to them (§32.4).

§32.4 states four things about each type — what it is, how consent works, when
it may be retrieved, and how fast it decays — and this module is all four as
data. `chat_orchestration` re-exports from here rather than keeping its own
copy: the memory module owns the taxonomy (§6.3), and two copies of an
11-member closed set is how the twelfth appears.

The numbering in the comments is §32.4's own, kept so a reader can check this
file against the spec line without translating names back to positions.
"""

from __future__ import annotations

import datetime as dt
import math

# The eleven IDS moved to `packages/schemas` in M8-P10 — `apps/web` needed them
# to render S18's memory chip, and the moment a closed set is named on both
# sides of the wire is the moment it needs one declaration. It had already
# drifted by then: `packages/i18n` carried a parallel eleven that seven labels
# disagreed with. This module still OWNS everything below — consent, the
# visibility gates, the decay policy are §6.3 the memory module's business and
# a schema package has no opinion about them.
from sitara_schemas.memory_types import MEMORY_TYPE_ORDER, MemoryType

# --------------------------------------------------------------------------
# Consent (§32.4: "all types explicit-chip; types 7–9 always re-confirm")
# --------------------------------------------------------------------------

#: Types 7, 8, 9. Their wording is re-confirmed with the user before saving —
#: a mood, a health-adjacent note or a money worry that Tara paraphrased badly
#: is worse than one she never kept.
RECONFIRM_WORDING: frozenset[MemoryType] = frozenset(
    {MemoryType.MOOD_PATTERN, MemoryType.HEALTH_ADJACENT, MemoryType.WORK_FINANCE}
)

# --------------------------------------------------------------------------
# Visibility gates (§32.4)
# --------------------------------------------------------------------------

#: Types 7–9: "retrieved only in matching conversational context".
CONTEXT_GATED: frozenset[MemoryType] = RECONFIRM_WORDING
#: Type 8: "never in celebratory/casual turns".
NEVER_IN_CASUAL: frozenset[MemoryType] = frozenset({MemoryType.HEALTH_ADJACENT})
#: Type 11: "always available".
ALWAYS_AVAILABLE: frozenset[MemoryType] = frozenset({MemoryType.PRONUNCIATION_IDENTITY})

# --------------------------------------------------------------------------
# Decay (§32.4: "4,7 decay fastest; 1,3,11 never auto-decay")
# --------------------------------------------------------------------------

#: Types the spec forbids auto-decaying: 1 person, 3 date/anniversary,
#: 11 pronunciation/identity. Who someone is does not go stale.
NEVER_DECAYS: frozenset[MemoryType] = frozenset(
    {MemoryType.PERSON, MemoryType.DATE_ANNIVERSARY, MemoryType.PRONUNCIATION_IDENTITY}
)

#: Half-life in days per type. §32.4 fixes the ORDERING — 4 and 7 fastest,
#: 1/3/11 never — not these numbers, which are engineering defaults tunable
#: from the admin console like any other. `test_taxonomy.py` asserts the
#: ordering the spec fixes, never the constants.
HALF_LIFE_DAYS: dict[MemoryType, float | None] = {
    MemoryType.PERSON: None,
    MemoryType.SIGNIFICANT_EVENT: 540.0,
    MemoryType.DATE_ANNIVERSARY: None,
    MemoryType.PREFERENCE: 60.0,
    MemoryType.GOAL_INTENTION: 120.0,
    MemoryType.DECISION_CONTEXT: 90.0,
    MemoryType.MOOD_PATTERN: 30.0,
    MemoryType.HEALTH_ADJACENT: 180.0,
    MemoryType.WORK_FINANCE: 180.0,
    MemoryType.SPIRITUAL_PRACTICE: 365.0,
    MemoryType.PRONUNCIATION_IDENTITY: None,
}

#: Below this a memory stops being retrieved. It is NOT deleted: §32.4 retains
#: "until user deletes", and §30.5 makes deletion the user's act alone. A
#: decayed memory is quiet, not gone — and the vault still shows it.
RETRIEVAL_FLOOR = 0.15


def decay_score(memory_type: MemoryType, *, age_days: float) -> float:
    """Exponential decay on the type's half-life. 1.0 for never-decay types."""
    half_life = HALF_LIFE_DAYS[memory_type]
    if half_life is None:
        return 1.0
    return round(math.pow(0.5, max(0.0, age_days) / half_life), 6)


def age_days(since: dt.datetime, now: dt.datetime) -> float:
    return max(0.0, (now - since).total_seconds() / 86400.0)


# --------------------------------------------------------------------------
# Type 8's classification rule (§32.4)
# --------------------------------------------------------------------------

#: §32.4: health-adjacent is "non-medical framing; NEVER symptoms/diagnoses —
#: those are declined at classification". This is that decline, as a lexicon.
#: It is deliberately blunt: refusing to store a borderline note costs the user
#: little, and storing a diagnosis would make Tara a medical record.
_MEDICAL_MARKERS: tuple[str, ...] = (
    "diagnos",
    "symptom",
    "prescrib",
    "medication",
    "dosage",
    "mg ",
    "tumour",
    "tumor",
    "cancer",
    "biopsy",
    "chemo",
    "blood pressure",
    "blood sugar",
    "cholesterol",
    "depression diagnosis",
    "bipolar",
    "schizophren",
    "निदान",
    "लक्षण",
    "दवा",
    "बीमारी",
)


def is_medical_content(content: str) -> bool:
    """True when §32.4 requires the candidate be declined at classification."""
    lowered = content.lower()
    return any(marker in lowered for marker in _MEDICAL_MARKERS)


__all__ = [
    "ALWAYS_AVAILABLE",
    "CONTEXT_GATED",
    "HALF_LIFE_DAYS",
    "MEMORY_TYPE_ORDER",
    "NEVER_DECAYS",
    "NEVER_IN_CASUAL",
    "RECONFIRM_WORDING",
    "RETRIEVAL_FLOOR",
    "MemoryType",
    "age_days",
    "decay_score",
    "is_medical_content",
]
