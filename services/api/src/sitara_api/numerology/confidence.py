"""§5.4 confidence state for a numerology reading.

Numerology needs no birth TIME — the date alone is exact — so a complete date
of birth yields Verified. What varies is whether the name is available and
confirmed, which determines whether name-number facts exist at all.

Confidence is computed here (step 3/6 of §5.3), stored on the guidance record
and rendered as a ConfidenceChip. It is never fabricated upward.
"""

from sitara_schemas.facts import ConfidenceState, FactKind, FactSnapshot


def confidence_for(facts: list[FactSnapshot]) -> ConfidenceState:
    kinds = {f.kind for f in facts}
    if not {FactKind.NUMEROLOGY_MOOLANK, FactKind.NUMEROLOGY_BHAGYANK} <= kinds:
        # No date of birth → nothing personal can be computed (§5.4 row 5).
        return ConfidenceState.CANNOT_CALCULATE
    if FactKind.NUMEROLOGY_NAME_NUMBER in kinds:
        # Exact date + a name the user confirmed (§22.10): fully grounded.
        return ConfidenceState.VERIFIED
    # Date-only: the numbers we give are exact, but the name-derived half of
    # the reading is missing — honest framing, not a downgrade of what we have.
    return ConfidenceState.VERIFIED_LIMITED_BIRTH_DATA
