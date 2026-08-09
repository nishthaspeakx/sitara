"""Onboarding — §6.3's "users/profiles" and "birth-details" contexts, scoped to
the §24.4 stack (S02–S13).

    types.py     the two closed sets: the thirteen steps and the four degrades
    service.py   per-step persistence and §24.4's resume; §13's write door
    reading.py   S13's composer — template-only, cite-or-die, no model
    router.py    the endpoints the screens call

Chart facts arrive through `AstrologyFacade` and calendar facts through
`PanchangService`; nothing here talks to an engine directly.
"""

from sitara_api.onboarding.service import OnboardingService, OnboardingState, StepAnswers
from sitara_api.onboarding.types import (
    DegradeReason,
    FirstReading,
    LineId,
    OnboardingStep,
    ReadingLine,
    ReadingStatus,
)

__all__ = [
    "DegradeReason",
    "FirstReading",
    "LineId",
    "OnboardingService",
    "OnboardingState",
    "OnboardingStep",
    "ReadingLine",
    "ReadingStatus",
    "StepAnswers",
]
