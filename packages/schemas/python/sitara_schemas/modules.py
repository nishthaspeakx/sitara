"""GENERATED FILE — do not edit. Source: packages/schemas/src/*.json (run scripts/generate.py)."""

from enum import StrEnum


class MorningModule(StrEnum):
    """SPEC §7.1 / §34.3 — the canonical 17 morning modules (closed set).

    The ranking engine emits ONLY these IDs.
    """

    ENERGY_OF_DAY = "energy_of_day"
    PERSONAL_CHART_THEME = "personal_chart_theme"
    MOON_NAKSHATRA_NOTE = "moon_nakshatra_note"
    COLOUR = "colour"
    NUMBER = "number"
    FAVOURABLE_WINDOW = "favourable_window"
    CAUTION_WINDOW = "caution_window"
    PRIORITIES = "priorities"
    WHAT_TO_AVOID = "what_to_avoid"
    FOOD_AND_DRINK = "food_and_drink"
    WORK = "work"
    RELATIONSHIP = "relationship"
    FAMILY_REMINDER = "family_reminder"
    FESTIVAL_OBSERVANCE = "festival_observance"
    GOAL_CHECK = "goal_check"
    SPIRITUAL_PRACTICE = "spiritual_practice"
    TOMORROW_PREP_TEASER = "tomorrow_prep_teaser"


MORNING_MODULE_ORDER: tuple[MorningModule, ...] = (
    MorningModule.ENERGY_OF_DAY,
    MorningModule.PERSONAL_CHART_THEME,
    MorningModule.MOON_NAKSHATRA_NOTE,
    MorningModule.COLOUR,
    MorningModule.NUMBER,
    MorningModule.FAVOURABLE_WINDOW,
    MorningModule.CAUTION_WINDOW,
    MorningModule.PRIORITIES,
    MorningModule.WHAT_TO_AVOID,
    MorningModule.FOOD_AND_DRINK,
    MorningModule.WORK,
    MorningModule.RELATIONSHIP,
    MorningModule.FAMILY_REMINDER,
    MorningModule.FESTIVAL_OBSERVANCE,
    MorningModule.GOAL_CHECK,
    MorningModule.SPIRITUAL_PRACTICE,
    MorningModule.TOMORROW_PREP_TEASER,
)
