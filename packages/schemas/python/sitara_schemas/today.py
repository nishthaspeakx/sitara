"""GENERATED FILE — do not edit. Source: packages/schemas/src/*.json (run scripts/generate.py).

SPEC §28.2 — the Today payload and the closed sets it carries.

`sitara_api.daily_guidance.types` imports Density, Tier, BriefStatus and
BriefDegradeReason FROM HERE rather than declaring its own. Both sides of
the wire need them, and a second declaration is how the two drift — the
same reason §34.3's MorningModule was never copied into the service.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from sitara_schemas.facts import ConfidenceState
from sitara_schemas.modules import MorningModule

__all__ = [
    "BriefDegradeReason",
    "BriefStatus",
    "Density",
    "PlanState",
    "TIME_BAND_STARTS",
    "Tier",
    "TimeBand",
    "TimingQuality",
    "TodayFestival",
    "TodayModule",
    "TodayPanchangEntry",
    "TodayPayload",
    "TodayState",
    "TodayTarasLine",
    "TodayTiming",
    "TodayTravel",
    "TodayTrust",
    "time_band",
]


class Density(StrEnum):
    """§28.2's three density modes. Default = the interest level captured at onboarding (S09). Density changes ranking-engine output COUNT, never facts."""

    LOW = "low"
    MED = "med"
    HIGH = "high"


class Tier(StrEnum):
    """§7.1's priority queues: paying > trial > dormant. DORMANT is the residual (CL-008 §2), never orthogonal to payment."""

    PAYING = "paying"
    TRIAL = "trial"
    DORMANT = "dormant"


class BriefStatus(StrEnum):
    """§7.1's four outcomes plus PENDING. RANKING_ONLY is the COST LEVER (and the §8 provider-outage path); VERIFIED_CORE_CARDS is the DEGRADE; FAILED is the row that could not reach even that. They are not interchangeable."""

    PENDING = "pending"
    POLISHED = "polished"
    RANKING_ONLY = "ranking_only"
    VERIFIED_CORE_CARDS = "verified_core_cards"
    FAILED = "failed"


class BriefDegradeReason(StrEnum):
    """Why a brief is not what it should have been. Recorded, never inferred. Distinct from the onboarding first-reading's own degrade reasons — a shared name would merge two different vocabularies."""

    GROUNDING_FAILED = "grounding_failed"
    LLM_UNAVAILABLE = "llm_unavailable"
    PANCHANG_UNAVAILABLE = "panchang_unavailable"
    CHART_UNAVAILABLE = "chart_unavailable"
    LANGUAGE_QUALITY_FAILED = "language_quality_failed"


class PlanState(StrEnum):
    """§28.2's four commercial variants. GRACE keeps full features (§30.3); FREE locks personal cards behind one calm CTA and never guilt-sells (§29.2)."""

    PREMIUM = "premium"
    TRIAL = "trial"
    FREE = "free"
    GRACE = "grace"


class TimingQuality(StrEnum):
    """§5.2's auspiciousness band, on the wire. The ENGINE's vocabulary, not the UI's — `TimingBar` speaks favourable/care/neutral and the screen maps between them, because §29.2 forbids fear-selling copy and 'inauspicious' is a fact about the sky rather than a word to put in front of someone."""

    AUSPICIOUS = "auspicious"
    NEUTRAL = "neutral"
    INAUSPICIOUS = "inauspicious"


class TimeBand(StrEnum):
    """§28.2's four time-of-day bands, as START minutes local. The thresholds are DECLARED here because both sides need them and they are spec rules, not preferences: the API composes Tara's line for the band, and the client renders the night takeover — '>20:00 the whole tab transforms'. Two hand-written copies of 20:00 is how a screen goes to dusk an hour after the sentence on it did."""

    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    NIGHT = "night"


#: Each band's first minute, local. Ordered latest-first so a lookup is
#: 'the first band whose start this time has reached'.
TIME_BAND_STARTS: tuple[tuple[TimeBand, str], ...] = (
    (TimeBand.NIGHT, "20:00"),
    (TimeBand.EVENING, "17:00"),
    (TimeBand.AFTERNOON, "12:00"),
    (TimeBand.MORNING, "00:00"),
)


def time_band(local_time: str) -> TimeBand:
    """§28.2's band for a zero-padded local "HH:MM". Never a UTC time."""
    for band, starts_at in TIME_BAND_STARTS:
        if local_time >= starts_at:
            return band
    return TimeBand.MORNING


class TodayTrust(BaseModel):
    """§30.4's three layers, already rendered. Fact IDs are absent BY SHAPE — there is no field one could travel in, which is the same guarantee TrustSheet's props give on the component side."""

    model_config = ConfigDict(frozen=True)

    plain: str
    sources_line: str
    details: tuple[str, ...]


class TodayModule(BaseModel):
    """One of §34.3's seventeen, composed and grounded. `text` is engine output — §5.3 forbids the LLM computing it and the composer put the citation inside the sentence before stripping it for the wire."""

    model_config = ConfigDict(frozen=True)

    module: MorningModule
    text: str
    confidence: ConfidenceState
    trust: TodayTrust


class TodayTarasLine(BaseModel):
    """§28.2 item (2) — 'one warm sentence for this moment', the emotional anchor, always present. NOT one of the seventeen and never rendered as a card."""

    model_config = ConfigDict(frozen=True)

    text: str
    confidence: ConfidenceState


class TodayPanchangEntry(BaseModel):
    """§28.2 item (6), shaped for the §24.3 PanchangStrip. `label_key` is an i18n key; `value` is a localised term the API resolved."""

    model_config = ConfigDict(frozen=True)

    label_key: str
    value: str


class TodayFestival(BaseModel):
    """§28.2's festival variant — the ONLY surface allowed above the core card, and suppressed to a core-card accent when two banners already show (§32.1)."""

    model_config = ConfigDict(frozen=True)

    name: str
    tradition_label: str
    date_label: str


class TodayTravel(BaseModel):
    """§30.2 Travel Mode. `city` is the place timings were recomputed for."""

    model_config = ConfigDict(frozen=True)

    active: bool
    city: str | None = None


class TodayState(BaseModel):
    """Everything §32.1's precedence rule reads, and nothing it does not. The rule itself lives on the client so there is exactly one implementation of it."""

    model_config = ConfigDict(frozen=True)

    first_session: bool
    first_morning: bool
    brief_time: str
    travel: TodayTravel
    festival: TodayFestival | None = None
    birthday: bool
    birth_time_missing: bool
    trial_day: int | None = None
    plan: PlanState
    story_ring_enabled: bool


class TodayTiming(BaseModel):
    """One day-timing window for S16 (§28.2 item 6 → /today/timings). Minutes-from-midnight because that is `TimingBar`'s axis unit; `range` is pre-formatted in the FACT's own zone (§5.3) so no client re-derives a clock from a timestamp and lands in the wrong one."""

    model_config = ConfigDict(frozen=True)

    name: str
    starts_minute: int
    ends_minute: int
    range: str
    quality: TimingQuality


class TodayPayload(BaseModel):
    """What GET /v1/today serves. `local_time` is DATA, not ambient: §28.2's night takeover fires after 20:00 LOCAL, and a screen that read the browser clock would render a different variant than the brief was generated for — and would make every §24.8 baseline depend on when CI ran."""

    model_config = ConfigDict(frozen=True)

    local_date: str
    local_time: str
    timezone: str
    density: Density
    tier: Tier
    status: BriefStatus
    degrade_reason: BriefDegradeReason | None = None
    confidence: ConfidenceState | None = None
    taras_line: TodayTarasLine | None = None
    modules: tuple[TodayModule, ...]
    panchang: tuple[TodayPanchangEntry, ...]
    state: TodayState
    timings: tuple[TodayTiming, ...]
    place_label: str | None = None
