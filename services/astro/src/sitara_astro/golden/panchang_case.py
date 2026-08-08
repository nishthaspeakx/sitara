"""Panchang golden-case format — same envelope as the other two suites.

§5.5's boundary threshold (≤2 min) governs every instant here. Two halves with
different standing, and the reviewer treats them differently (§35.3):

  * `sun`, `tithi`, `nakshatra` — deterministic astronomy, Layer A
    authoritative. A mismatch is an engine bug.
  * `day_timings`, `choghadiya` — tradition rule tables, DivineAPI primary for
    the served value. A mismatch may mean OUR TABLE is wrong, not our
    arithmetic, and the Jyotish lead's ruling on the table is the answer.

**Expected values are LOCAL time at the case's place**, deliberately: a
reviewer reads a published almanac in local time, and making them convert to
UTC invites exactly the error this suite exists to catch. A bare `HH:MM[:SS]`
means that time on the case's `local_date`; a full `YYYY-MM-DD HH:MM[:SS]`
carries its own date, which tithi and nakshatra edges need because they cross
midnight freely.
"""

import datetime as dt
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, ConfigDict, Field
from sitara_schemas.facts import Tradition

from sitara_astro.golden.case import (
    NEEDS_VERIFICATION,
    CaseSource,
    CaseStatus,
    _dumps,
    _fmt,
)

SCHEMA_VERSION = 1
REPO_PANCHANG_DIR = Path(__file__).resolve().parents[5] / "golden-set" / "panchang"
TARGET_CASE_COUNT = 200  # panchang slice of the §5.2 Layer-C 10,000

_LOCAL_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%H:%M:%S", "%H:%M")


class PanchangInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    local_date: dt.date
    place: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    tz: str
    tradition: Tradition = Tradition.AMANTA


class TzExpected(BaseModel):
    """Derived from the IANA tzdb — asserted every run, never astrology (§5.2)."""

    model_config = ConfigDict(validate_assignment=True)

    utc_offset: str | None = None
    ambiguous: bool = False


class SunExpected(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    sunrise_local: str | None = None
    sunset_local: str | None = None
    solar_noon_local: str | None = None


class TithiExpected(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    index_at_sunrise: int | None = Field(default=None, ge=1, le=30)
    paksha: str | None = None
    starts_local: str | None = None
    ends_local: str | None = None


class NakshatraExpected(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    name_at_sunrise: str | None = None
    starts_local: str | None = None
    ends_local: str | None = None


class BandExpected(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    starts_local: str | None = None
    ends_local: str | None = None


class DayTimingsExpected(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    rahu_kaal: BandExpected = Field(default_factory=BandExpected)
    yamaganda: BandExpected = Field(default_factory=BandExpected)
    gulikai: BandExpected = Field(default_factory=BandExpected)
    abhijit: BandExpected = Field(default_factory=BandExpected)


class ChoghadiyaExpected(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    first_day_part: str | None = None
    first_night_part: str | None = None


class PanchangExpected(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    sun: SunExpected = Field(default_factory=SunExpected)
    tithi: TithiExpected = Field(default_factory=TithiExpected)
    nakshatra: NakshatraExpected = Field(default_factory=NakshatraExpected)
    day_timings: DayTimingsExpected = Field(default_factory=DayTimingsExpected)
    choghadiya: ChoghadiyaExpected = Field(default_factory=ChoghadiyaExpected)


class PanchangCase(BaseModel):
    schema_version: int = SCHEMA_VERSION
    case_id: str = Field(pattern=r"^PC-\d{3}$")
    category: str
    status: CaseStatus = CaseStatus.PENDING
    source: CaseSource | None = None
    verified_by: str | None = None
    verified_on: dt.date | None = None
    notes: str = ""
    scope: str = "panchang"
    input: PanchangInput
    tz_expected: TzExpected = Field(default_factory=TzExpected)
    expected: PanchangExpected = Field(default_factory=PanchangExpected)


# Dotted paths the reviewer's CSV may write. Ordered as the file reads.
LEAF_FIELDS: tuple[str, ...] = (
    "sun.sunrise_local",
    "sun.sunset_local",
    "sun.solar_noon_local",
    "tithi.index_at_sunrise",
    "tithi.paksha",
    "tithi.starts_local",
    "tithi.ends_local",
    "nakshatra.name_at_sunrise",
    "nakshatra.starts_local",
    "nakshatra.ends_local",
    "day_timings.rahu_kaal.starts_local",
    "day_timings.rahu_kaal.ends_local",
    "day_timings.yamaganda.starts_local",
    "day_timings.yamaganda.ends_local",
    "day_timings.gulikai.starts_local",
    "day_timings.gulikai.ends_local",
    "day_timings.abhijit.starts_local",
    "day_timings.abhijit.ends_local",
    "choghadiya.first_day_part",
    "choghadiya.first_night_part",
)

# What a reviewer must have checked before `verify` will sign the case off.
# The astronomy block is Layer A's own output, so all of it is required; rahu
# kaal stands in for the tradition tables as the single most-consulted timing.
# Requiring all sixteen choghadiya parts would make sign-off impractical
# without materially raising confidence in the table.
REQUIRED_FIELDS: tuple[str, ...] = (
    "sun.sunrise_local",
    "sun.sunset_local",
    "tithi.index_at_sunrise",
    "tithi.paksha",
    "tithi.ends_local",
    "nakshatra.name_at_sunrise",
    "nakshatra.ends_local",
    "day_timings.rahu_kaal.starts_local",
    "day_timings.rahu_kaal.ends_local",
)

_INT_FIELDS = frozenset({"tithi.index_at_sunrise"})


def parse_local(value: str, case: PanchangCase) -> dt.datetime:
    """Reviewer's local-time string → aware datetime in the case's zone."""
    text = value.strip()
    for fmt in _LOCAL_FORMATS:
        try:
            parsed = dt.datetime.strptime(text, fmt)
        except ValueError:
            continue
        if "%Y" not in fmt:
            parsed = dt.datetime.combine(case.input.local_date, parsed.time())
        return parsed.replace(tzinfo=ZoneInfo(case.input.tz))
    raise ValueError(
        f"{case.case_id}: cannot read local time {value!r} — "
        "use 'HH:MM[:SS]' or 'YYYY-MM-DD HH:MM[:SS]'"
    )


def _get(case: PanchangCase, dotted: str) -> Any:
    cursor: Any = case.expected
    for part in dotted.split("."):
        cursor = getattr(cursor, part)
    return cursor


def _clean(node: Any) -> Any:
    """NEEDS_VERIFICATION on disk is None in the model, at any depth."""
    if isinstance(node, dict):
        return {k: _clean(v) for k, v in node.items()}
    return None if node == NEEDS_VERIFICATION else node


def parse_case(raw: dict[str, Any]) -> PanchangCase:
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"{raw.get('case_id', '?')}: unsupported schema_version")
    return PanchangCase.model_validate(
        {
            **raw,
            "notes": raw.get("notes") or "",
            "tz_expected": _clean(raw.get("tz_expected") or {}),
            "expected": _clean(raw.get("expected") or {}),
        }
    )


def load_case(path: Path | str) -> PanchangCase:
    return parse_case(yaml.safe_load(Path(path).read_text()))


def load_all(directory: Path | str = REPO_PANCHANG_DIR) -> list[PanchangCase]:
    paths = sorted(Path(directory).glob("PC-*.yaml"))
    if not paths:
        raise FileNotFoundError(f"no panchang cases in {directory}")
    return [load_case(p) for p in paths]


def dump_case(case: PanchangCase) -> str:
    e = case.expected
    inp = case.input
    return f"""schema_version: {case.schema_version}
case_id: {case.case_id}
category: {case.category}
status: {case.status.value}          # ONLY `golden verify` (a named human) may set this
source: {_fmt(case.source) if case.source else "null"}
verified_by: {_fmt(case.verified_by) if case.verified_by else "null"}
verified_on: {_fmt(case.verified_on) if case.verified_on else "null"}
notes: {_dumps(case.notes)}
scope: {case.scope}          # Layer-A astronomy + the Layer-B fallback rule tables
input:
  local_date: {_fmt(inp.local_date)}
  place: {_dumps(inp.place)}
  lat: {inp.lat}
  lon: {inp.lon}
  tz: {_dumps(inp.tz)}
  tradition: {inp.tradition.value}
  options:
    ayanamsa: lahiri
    node_type: mean
    rise_set: upper_limb_refracted
tz_expected:             # derived from IANA tzdb — asserted every run, not astrology
  utc_offset: {_fmt(case.tz_expected.utc_offset)}
  ambiguous: {str(case.tz_expected.ambiguous).lower()}
expected:                # fill ONLY from Drik Panchang / JHora, in LOCAL time
  # --- deterministic astronomy: Layer A is authoritative (§32.2, §35.3)
  sun:
    sunrise_local: {_fmt(e.sun.sunrise_local)}
    sunset_local: {_fmt(e.sun.sunset_local)}
    solar_noon_local: {_fmt(e.sun.solar_noon_local)}
  tithi:
    index_at_sunrise: {_fmt(e.tithi.index_at_sunrise)}      # 1-30; 1-15 shukla, 16-30 krishna
    paksha: {_fmt(e.tithi.paksha)}
    starts_local: {_fmt(e.tithi.starts_local)}
    ends_local: {_fmt(e.tithi.ends_local)}
  nakshatra:
    name_at_sunrise: {_fmt(e.nakshatra.name_at_sunrise)}
    starts_local: {_fmt(e.nakshatra.starts_local)}
    ends_local: {_fmt(e.nakshatra.ends_local)}
  # --- tradition RULE TABLES: DivineAPI is primary for the served value; these
  # verify our §8 fallback rung, and the tables themselves need Jyotish sign-off.
  day_timings:
    rahu_kaal:
      starts_local: {_fmt(e.day_timings.rahu_kaal.starts_local)}
      ends_local: {_fmt(e.day_timings.rahu_kaal.ends_local)}
    yamaganda:
      starts_local: {_fmt(e.day_timings.yamaganda.starts_local)}
      ends_local: {_fmt(e.day_timings.yamaganda.ends_local)}
    gulikai:
      starts_local: {_fmt(e.day_timings.gulikai.starts_local)}
      ends_local: {_fmt(e.day_timings.gulikai.ends_local)}
    abhijit:
      starts_local: {_fmt(e.day_timings.abhijit.starts_local)}
      ends_local: {_fmt(e.day_timings.abhijit.ends_local)}
  choghadiya:
    first_day_part: {_fmt(e.choghadiya.first_day_part)}        # e.g. kaal, shubh, rog…
    first_night_part: {_fmt(e.choghadiya.first_night_part)}
"""


def save_case(case: PanchangCase, path: Path | str) -> None:
    Path(path).write_text(dump_case(case))


def set_field(case: PanchangCase, dotted: str, raw_value: str) -> PanchangCase:
    if dotted not in LEAF_FIELDS:
        raise KeyError(f"unknown field path: {dotted!r}")
    updated = case.model_copy(deep=True)
    text = (raw_value or "").strip()
    value: Any = None if text in ("", NEEDS_VERIFICATION) else text
    if value is not None and dotted in _INT_FIELDS:
        value = int(value)
    *parents, leaf = dotted.split(".")
    cursor: Any = updated.expected
    for part in parents:
        cursor = getattr(cursor, part)
    setattr(cursor, leaf, value)
    return updated


def missing_required(case: PanchangCase) -> list[str]:
    return [f for f in REQUIRED_FIELDS if _get(case, f) is None]
