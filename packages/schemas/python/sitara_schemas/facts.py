"""HAND-WRITTEN MODULE — sanctioned exception to the generated-only rule (see CLAUDE.md).

SPEC §5.2 / §34.2 — the FactSnapshot contract emitted by the Layer-A engine.

Fact-IDs are logical keys, not foreign keys: there is deliberately no `facts`
collection. Every artefact that cites a fact embeds its full snapshot at
generation time; old artefacts read snapshots, never recomputations.
"""

import re
from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Literal, Union

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class Graha(StrEnum):
    """The nine grahas of the Vedic chart (closed set)."""

    SUN = "sun"
    MOON = "moon"
    MARS = "mars"
    MERCURY = "mercury"
    JUPITER = "jupiter"
    VENUS = "venus"
    SATURN = "saturn"
    RAHU = "rahu"
    KETU = "ketu"


class Rashi(StrEnum):
    """The twelve rashis (sidereal signs), Mesha-first (closed set)."""

    MESHA = "mesha"
    VRISHABHA = "vrishabha"
    MITHUNA = "mithuna"
    KARKA = "karka"
    SIMHA = "simha"
    KANYA = "kanya"
    TULA = "tula"
    VRISHCHIKA = "vrishchika"
    DHANU = "dhanu"
    MAKARA = "makara"
    KUMBHA = "kumbha"
    MEENA = "meena"


class Nakshatra(StrEnum):
    """The twenty-seven nakshatras, Ashwini-first (closed set)."""

    ASHWINI = "ashwini"
    BHARANI = "bharani"
    KRITTIKA = "krittika"
    ROHINI = "rohini"
    MRIGASHIRA = "mrigashira"
    ARDRA = "ardra"
    PUNARVASU = "punarvasu"
    PUSHYA = "pushya"
    ASHLESHA = "ashlesha"
    MAGHA = "magha"
    PURVA_PHALGUNI = "purva_phalguni"
    UTTARA_PHALGUNI = "uttara_phalguni"
    HASTA = "hasta"
    CHITRA = "chitra"
    SWATI = "swati"
    VISHAKHA = "vishakha"
    ANURADHA = "anuradha"
    JYESHTHA = "jyeshtha"
    MULA = "mula"
    PURVA_ASHADHA = "purva_ashadha"
    UTTARA_ASHADHA = "uttara_ashadha"
    SHRAVANA = "shravana"
    DHANISHTA = "dhanishta"
    SHATABHISHA = "shatabhisha"
    PURVA_BHADRAPADA = "purva_bhadrapada"
    UTTARA_BHADRAPADA = "uttara_bhadrapada"
    REVATI = "revati"


RASHI_ORDER: tuple[Rashi, ...] = tuple(Rashi)
NAKSHATRA_ORDER: tuple[Nakshatra, ...] = tuple(Nakshatra)


class FactKind(StrEnum):
    """Closed taxonomy of engine-emitted facts (M3). New kinds are PR-reviewed."""

    NATAL_GRAHA_POSITION = "natal.graha.position"
    NATAL_GRAHA_NAKSHATRA = "natal.graha.nakshatra"
    NATAL_LAGNA = "natal.lagna"
    NATAL_HOUSE_CUSPS = "natal.house.cusps"
    NATAL_GRAHA_HOUSE = "natal.graha.house"
    DASHA_VIMSHOTTARI_PERIOD = "dasha.vimshottari.period"
    TRANSIT_GRAHA_POSITION = "transit.graha.position"
    TRANSIT_GRAHA_HOUSE = "transit.graha.house"
    NUMEROLOGY_MOOLANK = "numerology.moolank"
    NUMEROLOGY_BHAGYANK = "numerology.bhagyank"
    NUMEROLOGY_NAME_NUMBER = "numerology.name_number"
    # M3 §5.2 Layer B/D. panchang.* boundary + rise/set facts are deterministic
    # astronomy (Layer A authoritative, §32.2); panchang.day_timing, muhurat.*
    # and festival.* are calendar interpretation (DivineAPI primary).
    PANCHANG_TITHI_BOUNDARY = "panchang.tithi.boundary"
    PANCHANG_NAKSHATRA_BOUNDARY = "panchang.nakshatra.boundary"
    PANCHANG_SUNRISE_SUNSET = "panchang.sunrise_sunset"
    PANCHANG_DAY_TIMING = "panchang.day_timing"
    MUHURAT_WINDOW = "muhurat.window"
    FESTIVAL_OBSERVANCE = "festival.observance"


class FactSource(StrEnum):
    """Which layer produced the SERVED value of a fact (§5.2, §32.2).

    Recorded on every snapshot so a Trust Sheet can state its provenance and so
    the Layer-D comparison job can never silently swap one source for another.
    """

    LAYER_A = "layer_a"
    DIVINEAPI = "divineapi"
    PROKERALA = "prokerala"


class Tradition(StrEnum):
    """Lunar-month reckoning — part of every §7.2 panchang cache key.

    Regional calendars (Tamil/Malayalam) arrive with the DivineAPI Prakash
    upgrade (§5.2 Layer B); this is the launch set.
    """

    AMANTA = "amanta"
    PURNIMANTA = "purnimanta"


class Paksha(StrEnum):
    """Lunar fortnight. Derived arithmetically from the tithi index, not named
    by a vendor: tithi 1–15 is shukla, 16–30 krishna."""

    SHUKLA = "shukla"
    KRISHNA = "krishna"


class DayTimingKind(StrEnum):
    """Sunrise-anchored day divisions (§5.2 Layer B: Rahu Kaal, Yamaganda,
    Gulikai; choghadiya/gowri panchangam from DivineAPI)."""

    RAHU_KAAL = "rahu_kaal"
    YAMAGANDA = "yamaganda"
    GULIKAI = "gulikai"
    ABHIJIT = "abhijit"
    CHOGHADIYA_DAY = "choghadiya_day"
    CHOGHADIYA_NIGHT = "choghadiya_night"


class Choghadiya(StrEnum):
    """The seven choghadiya names. The client maps these to i18n keys — a
    rendered name never crosses the wire (§2.4)."""

    UDVEG = "udveg"
    CHAR = "char"
    LABH = "labh"
    AMRIT = "amrit"
    KAAL = "kaal"
    SHUBH = "shubh"
    ROG = "rog"


class TimingQuality(StrEnum):
    """Auspiciousness band. Copy per §13/§29.2 is never fear-selling — the
    client renders `inauspicious` as a neutral caution, never a warning."""

    AUSPICIOUS = "auspicious"
    NEUTRAL = "neutral"
    INAUSPICIOUS = "inauspicious"


class MuhuratType(StrEnum):
    """DivineAPI's muhurat finder categories (§5.2 provider table)."""

    MARRIAGE = "marriage"
    GRIHA_PRAVESH = "griha_pravesh"
    VEHICLE = "vehicle"
    BUSINESS = "business"
    GENERAL = "general"


class DashaLevel(StrEnum):
    """Vimshottari dasha depth (closed set for M2)."""

    MAHA = "maha"
    ANTAR = "antar"
    PRATYANTAR = "pratyantar"


class NodeType(StrEnum):
    """Rahu/Ketu computation convention. Default mean (§5.2 defaults, reviewer-adjudicable)."""

    MEAN = "mean"
    TRUE = "true"


class BhavaSystem(StrEnum):
    """Cusp system for the computed bhava chart. Whole-sign remains the presented system."""

    SRIPATI = "sripati"
    PORPHYRY = "porphyry"
    EQUAL = "equal"
    PLACIDUS = "placidus"


class DashaYearBasis(StrEnum):
    """Year-length convention for vimshottari arithmetic."""

    DAYS_365_25 = "days_365_25"
    SIDEREAL_365_2564 = "sidereal_365_2564"
    SAVANA_360 = "savana_360"


class NumerologySystem(StrEnum):
    """Chaldean is primary, Pythagorean secondary (§5.5, §26.2 carry-forward)."""

    CHALDEAN = "chaldean"
    PYTHAGOREAN = "pythagorean"


class MasterNumberPolicy(StrEnum):
    """Whether 11/22/33 survive reduction. Default REDUCE (Indian convention);
    reviewer-adjudicable like every other engine convention."""

    REDUCE = "reduce"
    PRESERVE = "preserve"


class NameSource(StrEnum):
    """§22.10 provenance of the Latin string the Chaldean sum was taken over.
    A numerology fact may only be built from a name the user has confirmed."""

    LATIN_AS_ENTERED = "latin_as_entered"
    CONFIRMED_TRANSLITERATION = "confirmed_transliteration"
    USER_EDITED = "user_edited"


class ConfidenceState(StrEnum):
    """SPEC §5.4 — the five user-visible confidence states (closed set).

    Computed in the §5.3 pipeline, stored on every guidance record and rendered
    as a ConfidenceChip; it changes Tara's register but is never fabricated.
    """

    VERIFIED = "verified"
    VERIFIED_LIMITED_BIRTH_DATA = "verified_limited_birth_data"
    APPROXIMATE = "approximate"
    TRADITION_BASED_GENERAL = "tradition_based_general"
    CANNOT_CALCULATE = "cannot_calculate"


class EpheSource(StrEnum):
    """Which ephemeris backed a computation — recorded so a Moshier-computed
    fact is never mistaken for file-grade Swiss output.
    """

    SWISS_FILES = "swiss_files"
    MOSHIER = "moshier"


class FactPrecision(BaseModel):
    """Stated precision of the fact's value — never false precision (§5.3)."""

    model_config = ConfigDict(frozen=True)

    tolerance: float = Field(ge=0)
    unit: Literal["arc_sec", "second", "day", "exact"]


class TzMethod(BaseModel):
    """How the birth/transit instant was resolved from local time via IANA tzdb.

    Timezone handling is NEVER delegated to an external astrology API (§5.2).
    `ambiguous`/`gap_shifted_minutes` feed the §5.4 confidence downgrade upstream.
    """

    model_config = ConfigDict(frozen=True)

    tz: str
    utc_offset_seconds: int
    fold_used: Literal[0, 1] = 0
    ambiguous: bool = False
    gap_shifted_minutes: int = Field(default=0, ge=0)


class FactMethod(BaseModel):
    """The exact conventions a fact was computed under. Fields that do not
    apply to the fact's kind are None; what is set is what was used.
    """

    model_config = ConfigDict(frozen=True)

    ayanamsa: Literal["lahiri"] | None = None
    ephe_source: EpheSource | None = None
    node_type: NodeType | None = None
    house_presentation: Literal["whole_sign"] | None = None
    bhava_system: BhavaSystem | None = None
    dasha_year: DashaYearBasis | None = None
    tz: TzMethod | None = None
    # §5.2 Layer A rise/set. Default upper_limb_refracted — the definition
    # published almanacs use, so our sunrise matches the one a user can look up.
    rise_set: Literal["upper_limb_refracted", "disc_center"] | None = None
    tradition: Tradition | None = None
    # numerology (§22.10 / §5.5)
    numerology_system: NumerologySystem | None = None
    master_numbers: MasterNumberPolicy | None = None
    name_source: NameSource | None = None
    transliteration_scheme: Literal["iso15919"] | None = None


class GrahaPositionValue(BaseModel):
    """Sidereal ecliptic state of one graha at one instant."""

    model_config = ConfigDict(frozen=True)

    value_kind: Literal["graha_position"] = "graha_position"
    graha: Graha
    longitude_deg: float = Field(ge=0, lt=360)
    rashi: Rashi
    degrees_in_rashi: float = Field(ge=0, lt=30)
    speed_deg_per_day: float
    retrograde: bool


class NakshatraValue(BaseModel):
    """Nakshatra + pada occupied by a graha's longitude."""

    model_config = ConfigDict(frozen=True)

    value_kind: Literal["nakshatra"] = "nakshatra"
    graha: Graha
    nakshatra: Nakshatra
    nakshatra_index: int = Field(ge=1, le=27)
    pada: int = Field(ge=1, le=4)


class LagnaValue(BaseModel):
    """Sidereal ascendant."""

    model_config = ConfigDict(frozen=True)

    value_kind: Literal["lagna"] = "lagna"
    longitude_deg: float = Field(ge=0, lt=360)
    rashi: Rashi


class HouseCuspsValue(BaseModel):
    """Computed bhava chart: twelve madhya (cusp midpoints) and sandhi (boundaries)."""

    model_config = ConfigDict(frozen=True)

    value_kind: Literal["house_cusps"] = "house_cusps"
    system: BhavaSystem
    madhya_deg: tuple[float, ...] = Field(min_length=12, max_length=12)
    sandhi_deg: tuple[float, ...] = Field(min_length=12, max_length=12)


class HouseAssignmentValue(BaseModel):
    """House occupied by a graha — whole-sign (presented) and bhava (computed)."""

    model_config = ConfigDict(frozen=True)

    value_kind: Literal["house_assignment"] = "house_assignment"
    graha: Graha
    whole_sign_house: int = Field(ge=1, le=12)
    bhava: int = Field(ge=1, le=12)


class DashaPeriodValue(BaseModel):
    """One vimshottari period. parent_lords is () for maha, (maha,) for antar,
    (maha, antar) for pratyantar.
    """

    model_config = ConfigDict(frozen=True)

    value_kind: Literal["dasha_period"] = "dasha_period"
    level: DashaLevel
    lord: Graha
    start_utc: AwareDatetime
    end_utc: AwareDatetime
    parent_lords: tuple[Graha, ...] = Field(max_length=2)

    @model_validator(mode="after")
    def _check_depth(self) -> "DashaPeriodValue":
        expected = {DashaLevel.MAHA: 0, DashaLevel.ANTAR: 1, DashaLevel.PRATYANTAR: 2}
        if len(self.parent_lords) != expected[self.level]:
            raise ValueError(
                f"{self.level} period requires {expected[self.level]} parent lord(s), "
                f"got {len(self.parent_lords)}"
            )
        if self.end_utc <= self.start_utc:
            raise ValueError("end_utc must be after start_utc")
        return self


class MoolankValue(BaseModel):
    """Root number: the birth DAY reduced (§10-9 reveal moment)."""

    model_config = ConfigDict(frozen=True)

    value_kind: Literal["moolank"] = "moolank"
    value: int = Field(ge=1, le=33)
    birth_day: int = Field(ge=1, le=31)
    reduction_steps: tuple[int, ...] = Field(min_length=1)


class BhagyankValue(BaseModel):
    """Destiny number: every digit of the full birth date, reduced."""

    model_config = ConfigDict(frozen=True)

    value_kind: Literal["bhagyank"] = "bhagyank"
    value: int = Field(ge=1, le=33)
    digits: tuple[int, ...] = Field(min_length=8)  # yyyymmdd
    reduction_steps: tuple[int, ...] = Field(min_length=1)


class NameNumberValue(BaseModel):
    """Name number over the CONFIRMED Latin form (§22.10).

    `letter_values` is the full audit trail so a Trust Sheet can show the sum
    letter by letter — cite-or-die applies to numerology too (§5.3).
    """

    model_config = ConfigDict(frozen=True)

    value_kind: Literal["name_number"] = "name_number"
    system: NumerologySystem
    value: int = Field(ge=1, le=33)
    compound_value: int = Field(ge=1)
    latin_name: str = Field(min_length=1)
    letter_values: tuple[tuple[str, int], ...] = Field(min_length=1)
    reduction_steps: tuple[int, ...] = Field(min_length=1)


class _Window(BaseModel):
    """Shared start/end validation for every time-window fact."""

    model_config = ConfigDict(frozen=True)

    starts_utc: AwareDatetime
    ends_utc: AwareDatetime

    @model_validator(mode="after")
    def _check_window(self) -> "_Window":
        if self.ends_utc <= self.starts_utc:
            raise ValueError("ends_utc must be after starts_utc")
        return self


class TithiBoundaryValue(_Window):
    """The tithi running over a window, with the instants it opens and closes.

    Deterministic astronomy: the elongation crossing is found by bisection on
    our own ephemeris, so §32.2 makes Layer A authoritative here.
    """

    value_kind: Literal["tithi_boundary"] = "tithi_boundary"
    tithi_index: int = Field(ge=1, le=30)
    paksha: Paksha

    @model_validator(mode="after")
    def _check_paksha(self) -> "TithiBoundaryValue":
        expected = Paksha.SHUKLA if self.tithi_index <= 15 else Paksha.KRISHNA
        if self.paksha is not expected:
            raise ValueError(f"tithi {self.tithi_index} is {expected}, not {self.paksha}")
        return self


class NakshatraBoundaryValue(_Window):
    """The nakshatra the Moon occupies over a window, with its edge instants."""

    value_kind: Literal["nakshatra_boundary"] = "nakshatra_boundary"
    nakshatra: Nakshatra
    nakshatra_index: int = Field(ge=1, le=27)

    @model_validator(mode="after")
    def _check_index(self) -> "NakshatraBoundaryValue":
        if NAKSHATRA_ORDER[self.nakshatra_index - 1] is not self.nakshatra:
            raise ValueError(f"nakshatra_index {self.nakshatra_index} is not {self.nakshatra}")
        return self


class SunriseSunsetValue(BaseModel):
    """Rise/set/solar-noon for one local date at one place.

    `next_sunrise_utc` closes the night, so night choghadiya needs no second
    lookup. A place-date with no rise or no set (polar) never produces this
    fact — the engine declines rather than inventing one (§5.3).
    """

    model_config = ConfigDict(frozen=True)

    value_kind: Literal["sunrise_sunset"] = "sunrise_sunset"
    sunrise_utc: AwareDatetime
    sunset_utc: AwareDatetime
    solar_noon_utc: AwareDatetime
    next_sunrise_utc: AwareDatetime

    @model_validator(mode="after")
    def _check_order(self) -> "SunriseSunsetValue":
        if not (self.sunrise_utc < self.solar_noon_utc < self.sunset_utc < self.next_sunrise_utc):
            raise ValueError("sunrise < solar_noon < sunset < next_sunrise is required")
        return self


class DayTimingValue(_Window):
    """One sunrise-anchored window: a rahu-kaal band or a choghadiya part."""

    value_kind: Literal["day_timing"] = "day_timing"
    timing: DayTimingKind
    quality: TimingQuality
    choghadiya: Choghadiya | None = None
    part_index: int | None = Field(default=None, ge=1, le=8)

    @model_validator(mode="after")
    def _check_choghadiya(self) -> "DayTimingValue":
        is_chogh = self.timing in (DayTimingKind.CHOGHADIYA_DAY, DayTimingKind.CHOGHADIYA_NIGHT)
        if is_chogh and (self.choghadiya is None or self.part_index is None):
            raise ValueError("choghadiya timings require choghadiya + part_index")
        if not is_chogh and self.choghadiya is not None:
            raise ValueError(f"{self.timing} must not carry a choghadiya name")
        return self


class MuhuratWindowValue(_Window):
    """One muhurat window, labelled with the place it was computed FOR (§30.2).

    place_label/place_tz are carried on the fact itself so a window computed for
    "wedding in Jaipur" can never be rendered as if it were the user's own city.
    """

    value_kind: Literal["muhurat_window"] = "muhurat_window"
    muhurat_type: MuhuratType
    quality: TimingQuality
    place_label: str = Field(min_length=1, max_length=120)
    place_tz: str = Field(min_length=1)


class FestivalObservanceValue(BaseModel):
    """A festival/observance on one local date for one region+tradition.

    `festival_id` is a stable slug; the client resolves it to in-locale copy —
    a vendor's English festival name never reaches a user (§2.4).
    """

    model_config = ConfigDict(frozen=True)

    value_kind: Literal["festival_observance"] = "festival_observance"
    festival_id: str = Field(pattern=r"^[a-z0-9_]+$", max_length=64)
    date_local: date
    region: str = Field(pattern=r"^[a-z0-9_-]+$", max_length=32)
    tradition: Tradition


FactValue = Annotated[
    Union[
        GrahaPositionValue,
        NakshatraValue,
        LagnaValue,
        HouseCuspsValue,
        HouseAssignmentValue,
        DashaPeriodValue,
        MoolankValue,
        BhagyankValue,
        NameNumberValue,
        TithiBoundaryValue,
        NakshatraBoundaryValue,
        SunriseSunsetValue,
        DayTimingValue,
        MuhuratWindowValue,
        FestivalObservanceValue,
    ],
    Field(discriminator="value_kind"),
]

KIND_VALUE_KIND: dict[FactKind, str] = {
    FactKind.NATAL_GRAHA_POSITION: "graha_position",
    FactKind.NATAL_GRAHA_NAKSHATRA: "nakshatra",
    FactKind.NATAL_LAGNA: "lagna",
    FactKind.NATAL_HOUSE_CUSPS: "house_cusps",
    FactKind.NATAL_GRAHA_HOUSE: "house_assignment",
    FactKind.DASHA_VIMSHOTTARI_PERIOD: "dasha_period",
    FactKind.TRANSIT_GRAHA_POSITION: "graha_position",
    FactKind.TRANSIT_GRAHA_HOUSE: "house_assignment",
    FactKind.NUMEROLOGY_MOOLANK: "moolank",
    FactKind.NUMEROLOGY_BHAGYANK: "bhagyank",
    FactKind.NUMEROLOGY_NAME_NUMBER: "name_number",
    FactKind.PANCHANG_TITHI_BOUNDARY: "tithi_boundary",
    FactKind.PANCHANG_NAKSHATRA_BOUNDARY: "nakshatra_boundary",
    FactKind.PANCHANG_SUNRISE_SUNSET: "sunrise_sunset",
    FactKind.PANCHANG_DAY_TIMING: "day_timing",
    FactKind.MUHURAT_WINDOW: "muhurat_window",
    FactKind.FESTIVAL_OBSERVANCE: "festival_observance",
}

# fact:<kind_path>/<scope>/<subject>@v<chart_version>
# e.g. fact:transit.saturn.house/2026-07-28/user123@v3 (SPEC §5.2)
# kind_path interpolates the concrete graha/lord; scope is "natal", an ISO date,
# or a dasha-period start date; subject is an opaque caller-supplied reference.
FACT_ID_PATTERN = re.compile(
    r"^fact:(?P<kind_path>[a-z0-9_]+(?:\.[a-z0-9_]+)+)"
    r"/(?P<scope>[a-z0-9_-]+)"
    r"/(?P<subject>[A-Za-z0-9_-]+)"
    r"@v(?P<chart_version>\d+)$"
)


def build_fact_id(kind_path: str, scope: str, subject: str, chart_version: int) -> str:
    """Assemble a fact-ID and guarantee it matches FACT_ID_PATTERN."""
    fact_id = f"fact:{kind_path}/{scope}/{subject}@v{chart_version}"
    if not FACT_ID_PATTERN.match(fact_id):
        raise ValueError(f"malformed fact_id components: {fact_id!r}")
    return fact_id


class FactSnapshot(BaseModel):
    """SPEC §34.2 — the typed fact embedded in full in every citing artefact.

    valid_to semantics: None for natal facts (they die only by chart_version
    bump); period end for dasha; end of UTC day for transit houses; equal to
    valid_from for point-valid transit positions.
    """

    model_config = ConfigDict(frozen=True)

    fact_id: str
    kind: FactKind
    value: FactValue
    precision: FactPrecision
    method: FactMethod
    valid_from: AwareDatetime
    valid_to: AwareDatetime | None
    engine_semver: str
    data_revision: str
    # §5.2 describes a snapshot as (id, value, source, confidence). Defaulted so
    # every artefact written before M3 stays valid on read.
    source: FactSource = FactSource.LAYER_A
    confidence: ConfidenceState | None = None

    @field_validator("fact_id")
    @classmethod
    def _check_fact_id(cls, v: str) -> str:
        if not FACT_ID_PATTERN.match(v):
            raise ValueError(f"fact_id does not match grammar: {v!r}")
        return v

    @model_validator(mode="after")
    def _check_consistency(self) -> "FactSnapshot":
        expected = KIND_VALUE_KIND[self.kind]
        if self.value.value_kind != expected:
            raise ValueError(
                f"kind {self.kind} requires value_kind {expected!r}, "
                f"got {self.value.value_kind!r}"
            )
        match = FACT_ID_PATTERN.match(self.fact_id)
        assert match is not None  # guaranteed by _check_fact_id
        domain = self.kind.split(".", 1)[0]
        if not match["kind_path"].startswith(f"{domain}."):
            raise ValueError(
                f"fact_id kind_path {match['kind_path']!r} does not belong to "
                f"kind domain {domain!r}"
            )
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to must not precede valid_from")
        return self


__all__ = [
    "FACT_ID_PATTERN",
    "KIND_VALUE_KIND",
    "NAKSHATRA_ORDER",
    "RASHI_ORDER",
    "BhagyankValue",
    "BhavaSystem",
    "Choghadiya",
    "ConfidenceState",
    "DashaLevel",
    "DashaPeriodValue",
    "DashaYearBasis",
    "DayTimingKind",
    "DayTimingValue",
    "EpheSource",
    "FactKind",
    "FactMethod",
    "FactPrecision",
    "FactSnapshot",
    "FactSource",
    "FactValue",
    "FestivalObservanceValue",
    "Graha",
    "GrahaPositionValue",
    "HouseAssignmentValue",
    "HouseCuspsValue",
    "LagnaValue",
    "MasterNumberPolicy",
    "MoolankValue",
    "MuhuratType",
    "MuhuratWindowValue",
    "Nakshatra",
    "NakshatraBoundaryValue",
    "NakshatraValue",
    "NameNumberValue",
    "NameSource",
    "NodeType",
    "NumerologySystem",
    "Paksha",
    "Rashi",
    "SunriseSunsetValue",
    "TimingQuality",
    "TithiBoundaryValue",
    "Tradition",
    "TzMethod",
    "build_fact_id",
]
