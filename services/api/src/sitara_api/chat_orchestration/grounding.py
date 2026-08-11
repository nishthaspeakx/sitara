"""Stage 9 — the grounding validator (§5.3 step 9, §9).

"every claim cites a fact-ID; numbers match facts verbatim".

The contract with the model is one line of grammar: an astrological claim ends
with `[[fact:...]]`. Everything else here is enforcement, and it is deliberately
mechanical — a model that is asked nicely to cite will usually cite, and
"usually" is not what §5.3 promises. Three ways to fail:

1. a claim-bearing sentence with no citation at all;
2. a citation naming a fact-ID that is not in the served payload — the
   fabricated transit, which reads exactly like a real one;
3. a number in a cited sentence that does not appear in the cited snapshot.

The astrology lexicon that decides "claim-bearing" is derived from the
`sitara_schemas` enums, so the engine cannot grow a graha the validator does
not know about. `policy/claim_terms.json` adds the connective vocabulary per
locale.

WHAT COUNTS AS A CLAIM (CL-001, see docs/change-log.md)
-------------------------------------------------------
Naming a term is not the same as asserting something. Two sentences the spec
REQUIRES were failing validation and driving turns into the fallback line:
§2.3's first-use gloss of a tradition term, and §0.7's honesty about what the
facts do not cover. Both name a term; neither says anything about this
person's day.

So a sentence carrying a strong term is a claim UNLESS all five hold:

    no number · no clock value · no second-person reference ·
    no temporal deixis · no celestial entity asserted to be
    doing or being anything

Category terms — choghadiya, muhurat, tithi as CONCEPTS — may be glossed
uncited. A named body (graha, rashi, nakshatra) paired with a state or motion
verb is always a claim, in every locale.

Residual risks, stated rather than discovered later:

* **Bare tradition statements pass uncited.** "Muhurat selection is an old
  tradition" is exempt. It describes a practice, not a day. Narrower than it
  looks — "rahu kaal" is not exempt, because `rahu` is a graha name.
* **Subjecthood is approximated by co-occurrence.** A celestial name plus a
  state verb anywhere in the sentence counts, so "Saturn is the graha of
  discipline" is treated as a claim. That is the safe direction: a false
  positive costs one regeneration, a false negative ships a fabrication.
* **The marker lists are per-locale data.** A deictic or copula missing from
  `claim_terms.json` weakens the rule for that locale only, and silently.
  They are reviewed with the §14 language pass, like the safety corpora.
* **Sentence splitting is punctuation-based.** A claim welded to a gloss by a
  semicolon is judged as one sentence, and the citation requirement applies to
  the whole of it — strict, not lax.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo

from sitara_schemas.facts import (
    Choghadiya,
    FactSnapshot,
    Graha,
    Nakshatra,
    Paksha,
    Rashi,
)

from sitara_api import text as textutil
from sitara_api.chat_orchestration import config
from sitara_api.chat_orchestration.types import ValidatedFacts

#: The citation grammar. Nothing else is a citation.
CITATION_RE = re.compile(r"\[\[\s*(fact:[^\]\s]+)\s*\]\]")

_CLOCK_RE = re.compile(r"\b(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(am|pm)?\b", re.IGNORECASE)
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_DEVANAGARI_DIGITS = textutil.DEVANAGARI_DIGITS


#: Day-division names worth gating on. `choghadiya_day`/`choghadiya_night`
#: are covered by the plain locale term, and the generic quality words
#: ("general", "neutral") are excluded on purpose — they would flag ordinary
#: English sentences and make the validator useless by crying wolf.
_TIMING_TERMS: tuple[str, ...] = ("rahu kaal", "yamaganda", "gulikai", "abhijit")


@dataclass(frozen=True)
class _Markers:
    """The four things that turn a term-bearing sentence into a claim."""

    celestial: re.Pattern[str]
    state_motion: re.Pattern[str]
    second_person: re.Pattern[str]
    temporal: re.Pattern[str]
    absence: re.Pattern[str]
    celestial_compounds: re.Pattern[str]


@dataclass(frozen=True)
class CitedSentence:
    """One sentence that carried a citation the served payload could honour.

    §25.4 puts a fact-citation underline inside the bubble, and the validator
    is the only thing in the pipeline that knows WHICH words stand on a fact —
    it decided sentence by sentence, and then `strip_citations` erased the
    evidence. Recording it here is cheaper and far more honest than a second
    pass over the text guessing where the markers used to be.

    The `text` is the sentence WITHOUT its markers and without its terminal
    stop (the splitter consumes that), which is exactly the span to underline.
    """

    text: str
    fact_ids: tuple[str, ...]


@dataclass(frozen=True)
class GroundingVerdict:
    """Evidence, not an opinion. Frozen: the safety queue reads this later."""

    ok: bool
    clean_text: str
    cited_fact_ids: tuple[str, ...] = ()
    uncited_claims: tuple[str, ...] = ()
    unknown_fact_ids: tuple[str, ...] = ()
    numeric_mismatches: tuple[str, ...] = ()
    reasons: tuple[str, ...] = field(default_factory=tuple)
    #: In order of appearance. Empty on a rejected turn — a verdict that failed
    #: has no spans worth underlining, because its text never ships.
    cited_sentences: tuple[CitedSentence, ...] = ()


class GroundingValidator:
    def __init__(self, terms: dict[str, Any] | None = None) -> None:
        self._source = terms or config.claim_terms()
        self._lexicons: dict[str, tuple[re.Pattern[str], re.Pattern[str]]] = {}
        self._ordinals: dict[str, re.Pattern[str] | None] = {}
        self._ordinal_word_maps: dict[str, dict[str, int]] = {}
        self._markers_by_locale: dict[str, _Markers] = {}
        self._dates: dict[str, re.Pattern[str] | None] = {}

    def check(
        self, text: str, facts: ValidatedFacts | Sequence[FactSnapshot], locale: str
    ) -> GroundingVerdict:
        snapshots = facts.snapshots if isinstance(facts, ValidatedFacts) else tuple(facts)
        served = {snapshot.fact_id: snapshot for snapshot in snapshots}

        cited_ok: list[str] = []
        uncited: list[str] = []
        unknown: list[str] = []
        mismatches: list[str] = []
        reasons: list[str] = []
        spans: list[CitedSentence] = []

        for sentence in _sentences(text):
            citations = CITATION_RE.findall(sentence)
            bare = strip_citations(sentence)

            # An unknown fact-ID is a fabrication wherever it appears, so this
            # runs before the claim test rather than inside it.
            for fact_id in citations:
                if fact_id not in served:
                    unknown.append(fact_id)
                    reasons.append(f"cited fact-ID is not in the served payload: {fact_id}")
                elif fact_id not in cited_ok:
                    cited_ok.append(fact_id)

            if not self._is_claim(bare, locale):
                continue

            known = [fact_id for fact_id in citations if fact_id in served]
            if not known:
                uncited.append(bare)
                if not citations:
                    reasons.append(f"astrological claim with no citation: {_clip(bare)}")
                continue

            # §25.4's underline. Recorded for every claim-bearing sentence that
            # a served fact backs — which is precisely the set §30.4 requires
            # to be "reachable to a Trust Sheet in ≤1 tap".
            spans.append(CitedSentence(text=bare, fact_ids=tuple(dict.fromkeys(known))))

            house_pattern = self._ordinal_pattern(locale)
            for problem in _numeric_mismatches(
                bare,
                [served[fid] for fid in known],
                house_pattern,
                self._ordinal_words(locale),
            ):
                mismatches.append(problem)
                reasons.append(
                    f"number {problem} does not appear in the cited fact — "
                    f"§5.3 requires numbers verbatim"
                )

        ok = not (uncited or unknown or mismatches)
        return GroundingVerdict(
            ok=ok,
            clean_text=strip_citations(text),
            cited_fact_ids=tuple(cited_ok),
            uncited_claims=tuple(uncited),
            unknown_fact_ids=tuple(unknown),
            numeric_mismatches=tuple(mismatches),
            reasons=tuple(reasons),
            # A rejected turn's text never ships, so its spans are not worth
            # carrying — and carrying them would put a Trust Sheet behind a
            # sentence the pipeline is about to throw away.
            cited_sentences=tuple(spans) if ok else (),
        )

    # -- claim detection ---------------------------------------------------

    def _is_claim(self, sentence: str, locale: str) -> bool:
        """Is this sentence an astrological CLAIM, needing a fact-ID?

        The exemption (change-log 2026-08-08 · CL-001) exists because two
        sentences the spec REQUIRES were failing: §2.3's first-use gloss of a
        tradition term, and Tara's honesty about what her facts do not cover.
        Both name a term without asserting anything about this person's day.

        A sentence carrying a strong term is exempt only when ALL FIVE hold:
        no number · no clock · no second-person reference · no temporal
        deixis · no celestial entity asserted to be doing or being anything.
        Category terms may be glossed; a named body never goes uncited.
        """
        lowered = sentence.lower()
        normalised = lowered.translate(_DEVANAGARI_DIGITS)
        strong, weak = self._lexicon(locale)

        # An ordinal house is a claim on sight — "your 8th house" is the
        # classic fabrication and needs no other evidence.
        ordinal = self._ordinal_pattern(locale)
        if ordinal and ordinal.search(lowered):
            return True

        markers = self._markers(locale)
        # CL-002b: a calendar date is not an astrological number. Blank out
        # full date expressions before counting — but only those. A bare
        # ordinal is never a date, so "4th house" still fires below.
        without_dates = self._strip_dates(normalised, locale)
        has_number = bool(_NUMBER_RE.search(without_dates))
        has_clock = bool(_CLOCK_RE.search(without_dates))

        if weak.search(lowered) and has_number:
            return True
        if not strong.search(lowered):
            return False

        # -- strong term present ---------------------------------------------
        # The two guards on the absence exemption come FIRST, so a sentence
        # that admits to lacking one fact while asserting another is still a
        # claim: "I don't have rahu kaal, but Saturn is in your 10th" must
        # fail on the second clause.
        # "Rahu kaal" names a WINDOW, not the node. Blank the compounds out
        # before the celestial test, or "rahu kaal ka data nahin hai" reads as
        # an assertion about Rahu and the absence exemption never applies.
        celestial_probe = markers.celestial_compounds.sub(" ", lowered)
        if markers.celestial.search(celestial_probe) and markers.state_motion.search(lowered):
            return True
        if has_number or has_clock:
            return True

        # CL-002: a PURE absence-of-fact sentence is not a claim. Stating that
        # a fact is MISSING cannot be a fabrication — §5.3 forbids inventing
        # facts, not admitting to lacking one. This sits above the deixis test
        # on purpose: Hindi and Hinglish put "अभी"/"abhi" in these sentences
        # far more naturally than English does, and gating on that made Tara
        # unable to say what she did not know in two of three locales.
        if markers.absence.search(lowered):
            return False

        if markers.second_person.search(lowered) or markers.temporal.search(lowered):
            return True
        return False

    def _strip_dates(self, text: str, locale: str) -> str:
        pattern = self._date_pattern(locale)
        return pattern.sub(" ", text) if pattern else text

    def _date_pattern(self, locale: str) -> re.Pattern[str] | None:
        key = self._key(locale)
        if key not in self._dates:
            raw = self._source.get("date_expression_patterns", {}).get(key)
            self._dates[key] = re.compile(raw, re.IGNORECASE) if raw else None
        return self._dates[key]

    def _markers(self, locale: str) -> _Markers:
        key = self._key(locale)
        if key not in self._markers_by_locale:
            source = self._source

            def alt(section: str, *, derived: frozenset[str] = frozenset()) -> re.Pattern[str]:
                block = source.get(section, {})
                # English always joins the net: §2.3 keeps English loanwords in
                # Hinglish, and an English clause inside a Hindi reply asserts
                # just as hard as a Devanagari one.
                terms = set(block.get(key, ())) | set(block.get("en", ())) | set(derived)
                return _alternation(terms, min_length=2)

            self._markers_by_locale[key] = _Markers(
                celestial=alt("celestial", derived=_celestial_terms()),
                state_motion=alt("state_motion"),
                second_person=alt("second_person"),
                temporal=alt("temporal_deixis"),
                absence=alt("absence"),
                celestial_compounds=alt("celestial_compounds"),
            )
        return self._markers_by_locale[key]

    def _key(self, locale: str) -> str:
        return locale if locale in self._source["terms"] else "en"

    def _lexicon(self, locale: str) -> tuple[re.Pattern[str], re.Pattern[str]]:
        """(strong, weak) alternations: schema-derived names + locale terms."""
        key = self._key(locale)
        if key not in self._lexicons:
            entry = self._source["terms"].get(key, {})
            # English astrology vocabulary shows up inside a Hinglish reply by
            # design (§2.3 keeps loanwords), so English is always in the net.
            english = self._source["terms"].get("en", {})
            # A named body is at least as strong a signal as a tradition term.
            # Without this the Devanagari and Hinglish graha/rashi names are
            # absent from the strong set — the English ones arrive via
            # `_schema_terms` — and "चंद्रमा मीन राशि में है" reaches the
            # exemption test without ever tripping the strong gate.
            celestial = set(self._source.get("celestial", {}).get(key, ()))
            strong = (
                set(entry.get("strong", ()))
                | set(english.get("strong", ()))
                | _schema_terms()
                | celestial
            )
            weak = set(entry.get("weak", ())) | set(english.get("weak", ()))
            self._lexicons[key] = (_alternation(strong), _alternation(weak))
        return self._lexicons[key]

    def _ordinal_words(self, locale: str) -> dict[str, int]:
        """Word ordinal → house number, per locale.

        Needed because the §7.1 brief templates render house ordinals as WORDS
        in Hindi and Hinglish ("पहले भाव", not "1वें भाव" — a suffix rule is
        wrong for the first two houses). Without this map the pattern would
        still mark the sentence a claim, but the §5.3 numbers-verbatim check
        would have nothing to compare, and a polished line that rewrote
        "सातवें भाव" as "पहले भाव" would pass.
        """
        key = self._key(locale)
        if key not in self._ordinal_word_maps:
            block = self._source.get("ordinal_house_words", {}).get(key, {})
            self._ordinal_word_maps[key] = {
                word.lower(): number
                for word, number in block.items()
                if not word.startswith("$")
            }
        return self._ordinal_word_maps[key]

    def _ordinal_pattern(self, locale: str) -> re.Pattern[str] | None:
        key = self._key(locale)
        if key not in self._ordinals:
            raw = self._source.get("ordinal_house_patterns", {}).get(key)
            self._ordinals[key] = re.compile(raw, re.IGNORECASE) if raw else None
        return self._ordinals[key]


def _alternation(terms: Iterable[str], *, min_length: int = 3) -> re.Pattern[str]:
    """Whole-word alternation via the shared, script-aware helper.

    `min_length` drops to 2 for the marker sets — Hindi carries real signal in
    two characters ("है", "आज"), and dropping them would exempt exactly the
    sentences the rule is meant to catch.
    """
    return textutil.alternation(terms, min_length=min_length)


@lru_cache(maxsize=1)
def _celestial_terms() -> frozenset[str]:
    """Named bodies and points, from the engine's own enums.

    Grahas, rashis and nakshatras only — a choghadiya or a paksha is a WINDOW,
    not a body, and glossing one is exactly what the exemption permits.
    """
    names: set[str] = set()
    for enum in (Graha, Rashi, Nakshatra):
        names |= {member.value.replace("_", " ") for member in enum}
    return frozenset(names)


@lru_cache(maxsize=1)
def _schema_terms() -> frozenset[str]:
    """Every graha, rashi, nakshatra, choghadiya and paksha the engine knows.

    Derived rather than listed so a new enum member is gated the day it lands.
    """
    names: set[str] = set()
    for enum in (Graha, Rashi, Nakshatra, Choghadiya, Paksha):
        names |= {member.value.replace("_", " ") for member in enum}
    names |= set(_TIMING_TERMS)
    return frozenset(names)


# --------------------------------------------------------------------------
# Numbers
# --------------------------------------------------------------------------


def _house_number(token: str, words: dict[str, int]) -> str | None:
    """The house a matched ordinal token names — digits or word.

    None means "matched the pattern but resolves to no house", which the caller
    treats as a mismatch. Failing closed is right here: the token got past a
    pattern built from the locale's own ordinal list, so an unresolvable one is
    a lexicon that has drifted from the templates, and waving it through would
    silently retire the house check for that locale.
    """
    digits = "".join(ch for ch in token if ch.isdigit())
    if digits:
        return digits
    number = words.get(token.strip().lower())
    return str(number) if number is not None else None


def _numeric_mismatches(
    sentence: str,
    snapshots: Sequence[FactSnapshot],
    house_pattern: re.Pattern[str] | None = None,
    house_words: dict[str, int] | None = None,
) -> list[str]:
    """Every number in a cited sentence must come from a cited snapshot.

    Value numbers and temporal numbers are kept apart on purpose. A fact valid
    on the 8th of the month puts an 8 in play; if that 8 were allowed to
    satisfy "your 8th house", the validator would wave through a fabricated
    house on any date matching it. So a house ordinal must match a number the
    fact's VALUE carries, and nothing else.
    """
    value_numbers, temporal_numbers, allowed_clocks = _snapshot_values(snapshots)
    normalised = sentence.translate(_DEVANAGARI_DIGITS)

    problems: list[str] = []
    house_spans: list[tuple[int, int]] = []
    if house_pattern is not None:
        for match in house_pattern.finditer(normalised):
            house_spans.append(match.span())
            token = match.group(1)
            house = _house_number(token, house_words or {})
            if house is None or not _number_matches(house, value_numbers):
                problems.append(token)

    for match in _CLOCK_RE.finditer(normalised):
        if _clock_candidates(match) & allowed_clocks:
            continue
        problems.append(match.group(0).strip())

    # Clock times and house ordinals are settled above; blank them out so the
    # general pass does not judge the same digits by a second standard.
    remainder = _blank(_CLOCK_RE.sub(lambda m: " " * len(m.group(0)), normalised), house_spans)
    allowed = value_numbers | temporal_numbers
    for raw in _NUMBER_RE.findall(remainder):
        if not _number_matches(raw, allowed):
            problems.append(raw)
    return problems


def _blank(text: str, spans: Sequence[tuple[int, int]]) -> str:
    chars = list(text)
    for start, end in spans:
        for index in range(start, min(end, len(chars))):
            chars[index] = " "
    return "".join(chars)


def _number_matches(raw: str, allowed: set[float]) -> bool:
    """Verbatim, or the same value written to fewer decimal places.

    Rounding a fact is not fabricating one — §5.3's bar is that the number
    comes from the fact, and 12.4 for 12.437 does. Inventing 4 where the fact
    says 10 does not, which is the case this has to keep catching.
    """
    value = float(raw)
    if value in allowed:
        return True
    places = len(raw.split(".")[1]) if "." in raw else 0
    return any(round(candidate, places) == value for candidate in allowed)


def _snapshot_values(
    snapshots: Sequence[FactSnapshot],
) -> tuple[set[float], set[float], set[str]]:
    """(value numbers, temporal numbers, clock renderings) for the cited facts."""
    values: set[float] = set()
    temporal: set[float] = set()
    clocks: set[str] = set()
    for snapshot in snapshots:
        tz = ZoneInfo(snapshot.method.tz.tz) if snapshot.method.tz else dt.UTC
        _walk(snapshot.value.model_dump(), values, temporal, clocks, tz)
        for moment in (snapshot.valid_from, snapshot.valid_to):
            if moment is not None:
                _add_moment(moment, temporal, clocks, tz)
    return values, temporal, clocks


def _walk(
    value: Any, numbers: set[float], temporal: set[float], clocks: set[str], tz: Any
) -> None:
    match value:
        case bool():
            return
        case int() | float():
            numbers.add(float(value))
        case dt.datetime():
            _add_moment(value, temporal, clocks, tz)
        case dt.date():
            temporal.update({float(value.year), float(value.month), float(value.day)})
        case str():
            for found in _NUMBER_RE.findall(value):
                numbers.add(float(found))
        case dict():
            for item in value.values():
                _walk(item, numbers, temporal, clocks, tz)
        case list() | tuple():
            for item in value:
                _walk(item, numbers, temporal, clocks, tz)


def _add_moment(moment: dt.datetime, temporal: set[float], clocks: set[str], tz: Any) -> None:
    """A time is stated in the fact's own zone — never in UTC (§5.3, §7.2)."""
    local = moment.astimezone(tz)
    temporal.update({float(local.year), float(local.month), float(local.day)})
    temporal.update({float(local.hour), float(local.minute)})
    clocks.update(_render_clock(local))


def _render_clock(local: dt.datetime) -> set[str]:
    hour24, minute = local.hour, local.minute
    hour12 = hour24 % 12 or 12
    return {
        f"{hour24}:{minute:02d}",
        f"{hour24:02d}:{minute:02d}",
        f"{hour12}:{minute:02d}",
        f"{hour12:02d}:{minute:02d}",
    }


def _clock_candidates(match: re.Match[str]) -> set[str]:
    hour, minute = int(match.group(1)), match.group(2)
    meridiem = (match.group(4) or "").lower()
    written = {f"{hour}:{minute}", f"{hour:02d}:{minute}"}
    if meridiem == "pm" and hour != 12:
        written |= {f"{hour + 12}:{minute}", f"{hour + 12:02d}:{minute}"}
    if meridiem == "am" and hour == 12:
        written |= {f"0:{minute}", f"00:{minute}"}
    return written


# --------------------------------------------------------------------------
# Text helpers
# --------------------------------------------------------------------------


def strip_citations(text: str) -> str:
    """Remove the markers. Fact-IDs are internal and never render (§30.4)."""
    without = CITATION_RE.sub("", text)
    without = re.sub(r"[ \t]+", " ", without)
    without = re.sub(r"\s+([.,;:!?।])", r"\1", without)
    return without.strip()


def _sentences(text: str) -> Iterable[str]:
    return textutil.sentences(text)


def _clip(text: str, limit: int = 80) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"
