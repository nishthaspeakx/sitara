"""Contracts for the §24.4 onboarding stack (S01–S13).

Two closed sets live here and both are the spec's own. `OnboardingStep` is the
thirteen screens of §24.4 in order — the stack is LINEAR (§28.1), so a step is
an ordinal and resume is "the lowest one not yet done". `DegradeReason` is the
four ways S13's ceremony is allowed to fall short, and it is closed because the
screen renders one honest sentence per reason: a fifth reason with no sentence
would surface as a blank where the explanation should be.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum

from sitara_schemas.facts import ConfidenceState, FactSnapshot


class OnboardingStep(IntEnum):
    """§24.4's thirteen, numbered as the spec numbers them.

    S01 is absent on purpose: the launch animation records no answer and gates
    nothing, so treating it as a step would make "completed steps" mean two
    different things (seen vs answered) and would put a resume target on a
    screen with nothing to resume.
    """

    LANGUAGE = 2
    AUTH = 3
    VERIFY = 4
    CONSENT = 5
    BIRTH = 6
    BIRTH_TIME = 7
    CITY = 8
    INTEREST = 9
    NAME = 10
    PRIORITIES = 11
    VOICE = 12
    READING = 13


#: The step a resumed stack lands on when nothing has been answered yet.
FIRST_STEP = OnboardingStep.LANGUAGE


class DegradeReason(StrEnum):
    """Why S13 is showing less than a complete reading.

    Each value has exactly one `start.reading.degraded.*` sentence, and
    `tests/onboarding/test_reading.py` asserts the two sets match — a reason
    without copy is a blank space on the most important screen in the product.
    """

    TIMEOUT = "timeout"
    INSUFFICIENT_BIRTH_DATA = "insufficient_birth_data"
    ENGINE_UNAVAILABLE = "engine_unavailable"
    PANCHANG_UNAVAILABLE = "panchang_unavailable"


class ReadingStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    #: Nothing true could be said. The screen shows an ErrorState and a way on;
    #: it never shows an empty ceremony.
    UNAVAILABLE = "unavailable"


class SourceState(StrEnum):
    """§30.4's three VerifiedSourceRow states, carried on the reading.

    S13 renders "computed from your chart · verified against 2 sources ✓", and
    that sentence is a CLAIM. The live M8 acceptance run caught it being false:
    both panchang vendors were unreachable, the calendar layer came from Layer A
    alone, and the ceremony still said two sources had agreed. Nothing failed —
    the fact was real, the citation resolved, and the badge lied.
    """

    DEFAULT = "default"  # two independent sources agreed
    SINGLE = "single"  # one source answered today
    DISPUTED = "disputed"  # sources differ; §32.2 adjudication pending


class LineId(StrEnum):
    """The three sentences §0.17's minute 3 is made of.

    The API returns these IDS, never message keys. A server-supplied message
    key cannot be verified by `i18n-lint` (it is invisible to a source scan),
    and the client would be rendering whatever string the server named — so a
    typo'd key reaches the user as a raw dotted path. An ID from a closed set,
    expanded client-side into a declared dynamic key, is checkable at both ends.
    """

    MOON_NAKSHATRA = "moon_nakshatra"
    OBSERVATION = "observation"
    PANCHANG = "panchang"


@dataclass(frozen=True)
class ReadingLine:
    """One composed sentence, and the facts it stands on.

    `fact_ids` is never empty for a claim-bearing line — §5.3's cite-or-die
    applies to the ceremony exactly as it applies to a brief, and the composer
    drops a line it cannot cite rather than shipping it bare.
    """

    id: LineId
    values: dict[str, str] = field(default_factory=dict)
    fact_ids: tuple[str, ...] = ()
    confidence: ConfidenceState = ConfidenceState.VERIFIED
    #: Only for OBSERVATION — selects the house-specific sentence (§0.17's
    #: "specific" requirement). None for every other line.
    house: int | None = None


@dataclass(frozen=True)
class FirstReading:
    """S13's payload.

    `facts` carries the FULL snapshots, not just ids — §34.2: "full snapshot
    embedded in every artefact at generation; no facts collection". The reading
    the user was shown must remain reconstructable after the engine has moved
    on.
    """

    status: ReadingStatus
    confidence: ConfidenceState
    #: What the §30.4 source row may honestly claim.
    source_state: SourceState = SourceState.DEFAULT
    lines: tuple[ReadingLine, ...] = ()
    facts: tuple[FactSnapshot, ...] = ()
    #: What was asked for and not obtained, named rather than inferred, so the
    #: screen can tell "no birth time" from "the engine is down" — they degrade
    #: to similar-looking readings and are not the same problem.
    missing: tuple[str, ...] = ()
    degrade_reason: DegradeReason | None = None
