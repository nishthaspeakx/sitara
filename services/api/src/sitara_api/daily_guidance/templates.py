"""Template composition — §7.1's step before the LLM ever sees anything.

    "ranking engine picks from the 17 modules → template composition + LLM
    polish (batched, low-temperature, prompt-cached) → grounding validation"

The order in that sentence is the whole design. Composition happens FIRST and
from facts alone, so the text that reaches the model is already true; polish is
then a rewrite of true text rather than an invention constrained after the
fact. That is also what makes §7.1's degrade cheap — "verified core cards
(panchang + one chart theme, no LLM)" is just this module's output with the
polish step skipped, not a separate rendering path.

Three rules hold every function below:

* **Slots are filled from `FactSnapshot` values, never from anything else.**
  A slot that cannot be filled from a fact drops its module (`None`), which is
  the same answer the ranking engine gives when the fact is missing entirely —
  ranking checks the KIND is present, composition checks this particular
  snapshot actually carries the value the sentence needs.
* **Every claim-bearing sentence carries its citation.** The composer appends
  `[[fact:…]]` because it knows exactly which snapshot each slot came from.
  The polish stage is told to preserve them and the grounding validator checks
  that it did — the same mechanism as a chat turn, deliberately, so there is
  one definition of "cited" in the service.
* **Times render in the FACT's own zone.** Never UTC and never the server's.
  `grounding._render_clock` accepts the zero-padded 24-hour form, so that is
  what is emitted; a time rendered in the wrong zone is both a lie and a
  numeric mismatch, and it fails the validator for the second reason while
  being wrong for the first.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Sequence
from zoneinfo import ZoneInfo

from sitara_schemas.facts import (
    BhagyankValue,
    DayTimingValue,
    FactSnapshot,
    FestivalObservanceValue,
    Graha,
    HouseAssignmentValue,
    MoolankValue,
    MuhuratWindowValue,
    NakshatraBoundaryValue,
    NakshatraValue,
    TimingQuality,
    TithiBoundaryValue,
)
from sitara_schemas.modules import MorningModule

from sitara_api.daily_guidance.ranking import RankedModule
from sitara_api.daily_guidance.types import ComposedModule
from sitara_api.localisation import MissingString, resolve

logger = logging.getLogger(__name__)

#: Bumped when a template's wording changes, so `notifications.template_version`
#: and the §23.8 per-template analytics can tell two renderings apart.
TEMPLATE_VERSION = "brief-v1"


def template_id(module: MorningModule) -> str:
    return f"{TEMPLATE_VERSION}.{module.value}"


# ---------------------------------------------------------------------------
# Value extraction — one small reader per value shape
# ---------------------------------------------------------------------------
# Every reader narrows with `isinstance`, never by comparing `value_kind`.
# `FactValue` is a discriminated union and the string comparison does not narrow
# it, so `value.tithi_index` after a `value_kind == "tithi_boundary"` check is
# unchecked at the type level — the reader would keep working right up until
# someone reordered the union and it started reading a field off the wrong
# member. `isinstance` makes the same intent checkable.


def _tithi(snapshots: Sequence[FactSnapshot]) -> tuple[FactSnapshot, int, str] | None:
    for snapshot in snapshots:
        value = snapshot.value
        if isinstance(value, TithiBoundaryValue):
            return snapshot, value.tithi_index, value.paksha.value
    return None


def _nakshatra(snapshots: Sequence[FactSnapshot]) -> tuple[FactSnapshot, str] | None:
    """The MOON's nakshatra, and no other body's.

    The graha check is the whole function. `natal.graha.nakshatra` is emitted
    for all nine grahas and the Sun's arrives first, so taking the first
    nakshatra-shaped value produced "The Moon sits in Purva Bhadrapada" citing
    the SUN's nakshatra — a false sentence with a real citation, which is the
    exact failure the citation machinery exists to prevent and cannot catch:
    the id IS in the payload and the name DOES match the fact it names.

    A `NakshatraBoundaryValue` carries no graha because it is the panchang's
    nakshatra, which is the Moon's by definition (§5.2); a `NakshatraValue`
    carries one and must be the Moon's to be this card.
    """
    for snapshot in snapshots:
        value = snapshot.value
        if isinstance(value, NakshatraBoundaryValue):
            return snapshot, value.nakshatra.value
        if isinstance(value, NakshatraValue) and value.graha is Graha.MOON:
            return snapshot, value.nakshatra.value
    return None


def _house(
    snapshots: Sequence[FactSnapshot], *, prefer: Sequence[str] = ()
) -> tuple[FactSnapshot, str, int] | None:
    """A graha and the house it occupies.

    `prefer` lets a module ask for the body its card is actually about — Venus
    for the relationship card — without inventing one when it is absent. The
    fallback is the first house assignment we have, because a true sentence
    about Saturn is better than no card, and both are honest.
    """
    assignments = [
        (s, s.value) for s in snapshots if isinstance(s.value, HouseAssignmentValue)
    ]
    for wanted in prefer:
        for snapshot, value in assignments:
            if value.graha.value == wanted:
                return snapshot, wanted, value.whole_sign_house
    if assignments:
        snapshot, value = assignments[0]
        return snapshot, value.graha.value, value.whole_sign_house
    return None


def _number(snapshots: Sequence[FactSnapshot]) -> tuple[FactSnapshot, int] | None:
    for snapshot in snapshots:
        value = snapshot.value
        if isinstance(value, MoolankValue | BhagyankValue):
            return snapshot, value.value
    return None


def _window(
    snapshots: Sequence[FactSnapshot], *, qualities: Sequence[TimingQuality]
) -> tuple[FactSnapshot, dt.datetime, dt.datetime, str | None] | None:
    """The first window whose quality the caller asked for.

    Returns the timing's own name where it has one (`rahu_kaal`), and None for
    a muhurat window, which is named by its type rather than by a day division.
    """
    for snapshot in snapshots:
        value = snapshot.value
        if isinstance(value, DayTimingValue) and value.quality in qualities:
            return snapshot, value.starts_utc, value.ends_utc, value.timing.value
        if isinstance(value, MuhuratWindowValue) and value.quality in qualities:
            return snapshot, value.starts_utc, value.ends_utc, None
    return None


def _festival(snapshots: Sequence[FactSnapshot]) -> tuple[FactSnapshot, str] | None:
    for snapshot in snapshots:
        value = snapshot.value
        if isinstance(value, FestivalObservanceValue):
            return snapshot, value.festival_id
    return None


def _clock(moment: dt.datetime, snapshot: FactSnapshot) -> str:
    """Zero-padded 24-hour local time, in the FACT's zone (§5.3, §7.2)."""
    zone = ZoneInfo(snapshot.method.tz.tz) if snapshot.method.tz else dt.UTC
    return moment.astimezone(zone).strftime("%H:%M")


def _term(kind: str, slug: str, locale: str) -> str | None:
    """Render a closed-set term in-locale, or decline.

    §2.4 forbids a silent English fallback, and this is precisely where one
    would creep in: a missing Devanagari nakshatra name is not "render the slug
    and move on", it is a card that cannot be written in this language today.
    Returning None drops the module, which is visible in the brief's shape and
    in the logs.
    """
    try:
        return resolve(f"terms.{kind}.{slug}", locale)
    except MissingString:
        logger.warning("brief term missing", extra={"kind": kind, "slug": slug, "locale": locale})
        return None


#: Sentence-final punctuation the citation must go BEFORE. The danda is in the
#: set because a Hindi sentence ends with it and nothing else.
_TERMINAL_PUNCTUATION = ".!?।"


def _cite(text: str, *snapshots: FactSnapshot) -> str:
    """Attach the markers INSIDE the sentence they belong to.

    Not a cosmetic choice. The grounding validator splits on punctuation, so
    `"Saturn is in your 10th house. [[fact:…]]"` is TWO sentences to it: an
    uncited claim followed by a bare marker — and it fails, correctly, on text
    that is in fact perfectly cited. Placing the marker before the full stop
    keeps claim and citation in one sentence, which is the shape the chat
    pipeline's contract already describes and the shape `strip_citations`
    already cleans up after (it collapses the space left before the stop).
    """
    markers = " ".join(f"[[{snapshot.fact_id}]]" for snapshot in snapshots)
    if not markers:
        return text
    stripped = text.rstrip()
    if stripped and stripped[-1] in _TERMINAL_PUNCTUATION:
        return f"{stripped[:-1].rstrip()} {markers}{stripped[-1]}"
    return f"{stripped} {markers}"


# ---------------------------------------------------------------------------
# The composer
# ---------------------------------------------------------------------------


class BriefComposer:
    """Turns ranked modules into cited, in-locale, engine-composed text.

    `inputs` carries the non-fact material for the three modules that have no
    astrological claim to make — the user's stated priorities, an open goal, a
    family occasion. They are rendered without a citation because there is
    nothing astrological in them to cite; the grounding validator agrees, since
    none of them names a celestial body.
    """

    def __init__(self, *, inputs: dict[str, str] | None = None) -> None:
        self._inputs = inputs or {}

    def compose_all(
        self, ranked: Sequence[RankedModule], locale: str
    ) -> list[ComposedModule]:
        out: list[ComposedModule] = []
        for item in ranked:
            composed = self.compose(item, locale)
            if composed is None:
                logger.info(
                    "brief module dropped at composition",
                    extra={"module": item.module.value, "locale": locale},
                )
                continue
            out.append(composed)
        return out

    def compose(self, ranked: RankedModule, locale: str) -> ComposedModule | None:
        builder = _BUILDERS.get(ranked.module)
        if builder is None:  # unreachable: _BUILDERS covers the closed 17
            return None
        built = builder(self, ranked.snapshots, locale)
        if built is None:
            return None
        text, cited = built
        return ComposedModule(
            module=ranked.module,
            text=text,
            snapshots=tuple(cited),
            template_id=template_id(ranked.module),
        )

    # -- per-module builders ------------------------------------------------
    # Each returns (text, snapshots actually cited) or None.

    def _tithi_line(
        self, key: MorningModule, snapshots: Sequence[FactSnapshot], locale: str
    ) -> tuple[str, list[FactSnapshot]] | None:
        found = _tithi(snapshots)
        if found is None:
            return None
        snapshot, index, paksha_slug = found
        paksha = _term("paksha", paksha_slug, locale)
        if paksha is None:
            return None
        text = resolve(f"brief.module.{key.value}", locale, paksha=paksha, tithi=index)
        return _cite(text, snapshot), [snapshot]

    def energy_of_day(self, snapshots, locale):  # noqa: ANN001, ANN201
        return self._tithi_line(MorningModule.ENERGY_OF_DAY, snapshots, locale)

    def food_and_drink(self, snapshots, locale):  # noqa: ANN001, ANN201
        return self._tithi_line(MorningModule.FOOD_AND_DRINK, snapshots, locale)

    def spiritual_practice(self, snapshots, locale):  # noqa: ANN001, ANN201
        return self._tithi_line(MorningModule.SPIRITUAL_PRACTICE, snapshots, locale)

    def colour(self, snapshots, locale):  # noqa: ANN001, ANN201
        found = _tithi(snapshots)
        if found is None:
            return None
        snapshot, _, paksha_slug = found
        paksha = _term("paksha", paksha_slug, locale)
        if paksha is None:
            return None
        text = resolve("brief.module.colour", locale, paksha=paksha)
        return _cite(text, snapshot), [snapshot]

    def tomorrow_prep_teaser(self, snapshots, locale):  # noqa: ANN001, ANN201
        found = _tithi(snapshots)
        if found is None:
            return None
        snapshot, index, _ = found
        text = resolve("brief.module.tomorrow_prep_teaser", locale, tithi=index)
        return _cite(text, snapshot), [snapshot]

    def moon_nakshatra_note(self, snapshots, locale):  # noqa: ANN001, ANN201
        found = _nakshatra(snapshots)
        if found is None:
            return None
        snapshot, slug = found
        name = _term("nakshatra", slug, locale)
        if name is None:
            return None
        text = resolve("brief.module.moon_nakshatra_note", locale, nakshatra=name)
        return _cite(text, snapshot), [snapshot]

    def _house_line(
        self,
        key: MorningModule,
        snapshots: Sequence[FactSnapshot],
        locale: str,
        *,
        prefer: Sequence[str] = (),
    ) -> tuple[str, list[FactSnapshot]] | None:
        found = _house(snapshots, prefer=prefer)
        if found is None:
            return None
        snapshot, graha_slug, house = found
        graha = _term("graha", graha_slug, locale)
        if graha is None:
            return None
        text = resolve(
            f"brief.module.{key.value}", locale, graha=graha, house=_ordinal(house, locale)
        )
        return _cite(text, snapshot), [snapshot]

    def personal_chart_theme(self, snapshots, locale):  # noqa: ANN001, ANN201
        return self._house_line(MorningModule.PERSONAL_CHART_THEME, snapshots, locale)

    def work(self, snapshots, locale):  # noqa: ANN001, ANN201
        return self._house_line(
            MorningModule.WORK, snapshots, locale, prefer=("saturn", "mercury", "sun")
        )

    def relationship(self, snapshots, locale):  # noqa: ANN001, ANN201
        return self._house_line(
            MorningModule.RELATIONSHIP, snapshots, locale, prefer=("venus", "moon")
        )

    def number(self, snapshots, locale):  # noqa: ANN001, ANN201
        found = _number(snapshots)
        if found is None:
            return None
        snapshot, value = found
        text = resolve("brief.module.number", locale, number=value)
        return _cite(text, snapshot), [snapshot]

    def favourable_window(self, snapshots, locale):  # noqa: ANN001, ANN201
        found = _window(snapshots, qualities=(TimingQuality.AUSPICIOUS,))
        if found is None:
            return None
        snapshot, start, end, _ = found
        text = resolve(
            "brief.module.favourable_window",
            locale,
            start=_clock(start, snapshot),
            end=_clock(end, snapshot),
        )
        return _cite(text, snapshot), [snapshot]

    def caution_window(self, snapshots, locale):  # noqa: ANN001, ANN201
        found = _window(snapshots, qualities=(TimingQuality.INAUSPICIOUS,))
        if found is None:
            return None
        snapshot, start, end, timing_slug = found
        if timing_slug is None:
            return None
        timing = _term("day_timing", timing_slug, locale)
        if timing is None:
            return None
        text = resolve(
            "brief.module.caution_window",
            locale,
            timing=timing,
            start=_clock(start, snapshot),
            end=_clock(end, snapshot),
        )
        return _cite(text, snapshot), [snapshot]

    def what_to_avoid(self, snapshots, locale):  # noqa: ANN001, ANN201
        found = _window(snapshots, qualities=(TimingQuality.INAUSPICIOUS,))
        if found is None:
            return None
        snapshot, start, end, _ = found
        text = resolve(
            "brief.module.what_to_avoid",
            locale,
            start=_clock(start, snapshot),
            end=_clock(end, snapshot),
        )
        return _cite(text, snapshot), [snapshot]

    def festival_observance(self, snapshots, locale):  # noqa: ANN001, ANN201
        found = _festival(snapshots)
        if found is None:
            return None
        snapshot, festival_id = found
        try:
            name = resolve(f"festivals.{festival_id}", locale)
        except MissingString:
            # §2.4: "a vendor's English festival name never reaches a user".
            # An unnamed festival is a card we cannot write, not a card we
            # write in the wrong language.
            logger.warning(
                "festival name missing in locale",
                extra={"festival_id": festival_id, "locale": locale},
            )
            return None
        text = resolve("brief.module.festival_observance", locale, festival=name)
        return _cite(text, snapshot), [snapshot]

    # -- the three fact-free modules (§28.2's contextual cards) -------------

    def priorities(self, snapshots, locale):  # noqa: ANN001, ANN201, ARG002
        value = self._inputs.get("priorities")
        if not value:
            return None
        return resolve("brief.module.priorities", locale, priority=value), []

    def goal_check(self, snapshots, locale):  # noqa: ANN001, ANN201, ARG002
        value = self._inputs.get("goals")
        if not value:
            return None
        return resolve("brief.module.goal_check", locale, goal=value), []

    def family_reminder(self, snapshots, locale):  # noqa: ANN001, ANN201, ARG002
        name = self._inputs.get("family_member")
        occasion = self._inputs.get("family_events")
        if not name or not occasion:
            return None
        return (
            resolve("brief.module.family_reminder", locale, name=name, occasion=occasion),
            [],
        )


#: English ordinals only where the locale's grammar wants one. The Hindi and
#: Hinglish templates carry their own suffix ("10वें", "10ve"), so the number
#: goes in bare and the sentence stays grammatical in its own language rather
#: than in a translated English one (§2.3).
def _ordinal(value: int, locale: str) -> str:
    if locale != "en":
        return str(value)
    if 10 <= value % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"


_BUILDERS = {
    MorningModule.ENERGY_OF_DAY: BriefComposer.energy_of_day,
    MorningModule.PERSONAL_CHART_THEME: BriefComposer.personal_chart_theme,
    MorningModule.MOON_NAKSHATRA_NOTE: BriefComposer.moon_nakshatra_note,
    MorningModule.COLOUR: BriefComposer.colour,
    MorningModule.NUMBER: BriefComposer.number,
    MorningModule.FAVOURABLE_WINDOW: BriefComposer.favourable_window,
    MorningModule.CAUTION_WINDOW: BriefComposer.caution_window,
    MorningModule.PRIORITIES: BriefComposer.priorities,
    MorningModule.WHAT_TO_AVOID: BriefComposer.what_to_avoid,
    MorningModule.FOOD_AND_DRINK: BriefComposer.food_and_drink,
    MorningModule.WORK: BriefComposer.work,
    MorningModule.RELATIONSHIP: BriefComposer.relationship,
    MorningModule.FAMILY_REMINDER: BriefComposer.family_reminder,
    MorningModule.FESTIVAL_OBSERVANCE: BriefComposer.festival_observance,
    MorningModule.GOAL_CHECK: BriefComposer.goal_check,
    MorningModule.SPIRITUAL_PRACTICE: BriefComposer.spiritual_practice,
    MorningModule.TOMORROW_PREP_TEASER: BriefComposer.tomorrow_prep_teaser,
}

assert set(_BUILDERS) == set(MorningModule), (
    "every §34.3 module needs a composer, or the ranking engine can emit a "
    "module nothing knows how to write"
)
