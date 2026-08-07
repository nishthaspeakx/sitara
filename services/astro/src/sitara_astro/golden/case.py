"""Versioned golden-case format (SPEC §5.5).

YAML on disk, Pydantic in memory. Unfilled expectations are the literal
NEEDS_VERIFICATION sentinel on disk and None in the model, so a reviewer can
see at a glance what still needs their eyes.
"""

import datetime as dt
import json
from datetime import date, datetime, time
from enum import StrEnum
from functools import partial
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sitara_schemas.facts import (
    BhavaSystem,
    DashaYearBasis,
    Graha,
    Nakshatra,
    NodeType,
    Rashi,
)

SCHEMA_VERSION = 2  # v1 = the P3a seed shape (nested input.birth.place)
NEEDS_VERIFICATION = "NEEDS_VERIFICATION"

GRAHA_ORDER: tuple[str, ...] = tuple(g.value for g in Graha)
DASHA_SLOTS: tuple[str, ...] = ("maha_at_birth", "antar_at_birth")
# .../services/astro/src/sitara_astro/golden/case.py → repo root is 5 levels up
REPO_CASES_DIR = Path(__file__).resolve().parents[5] / "golden-set" / "cases"


class TimeAccuracy(StrEnum):
    """Drives the §5.4 confidence state a case exercises."""

    EXACT = "exact"
    WINDOW = "window"
    DATE_ONLY = "date_only"


class CaseSource(StrEnum):
    JHORA = "JHora"
    DRIK_PANCHANG = "DrikPanchang"
    JYOTISH_LEAD = "JyotishLead"


class CaseStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"


class GrahaExpectation(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    longitude_deg: float | None = Field(default=None, ge=0, lt=360)
    rashi: Rashi | None = None
    nakshatra: Nakshatra | None = None
    pada: int | None = Field(default=None, ge=1, le=4)


class LagnaExpectation(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    longitude_deg: float | None = Field(default=None, ge=0, lt=360)
    rashi: Rashi | None = None


class DashaExpectation(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    lord: Graha | None = None
    start: date | None = None
    end: date | None = None


class BoundaryExpectation(BaseModel):
    """§5.5 tithi/nakshatra boundary times (±2 min)."""

    model_config = ConfigDict(validate_assignment=True)

    moon_nakshatra_end_utc: AwareDatetime | None = None
    tithi_end_utc: AwareDatetime | None = None


class TransitExpectation(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    saturn_whole_sign_house: int | None = Field(default=None, ge=1, le=12)
    moon_nakshatra: Nakshatra | None = None


class Expected(BaseModel):
    grahas: dict[str, GrahaExpectation]
    lagna: LagnaExpectation
    dasha: dict[str, DashaExpectation]
    boundaries: BoundaryExpectation
    transit: TransitExpectation | None = None


class CaseOptions(BaseModel):
    model_config = ConfigDict(frozen=True)

    ayanamsa: Literal["lahiri"] = "lahiri"
    node_type: NodeType = NodeType.MEAN
    bhava_system: BhavaSystem = BhavaSystem.SRIPATI
    dasha_year: DashaYearBasis = DashaYearBasis.DAYS_365_25
    gap_policy: Literal["error", "shift_forward"] = "shift_forward"


class CaseInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    # dt.* aliases: the field names `date`/`time` shadow the bare type names
    date: dt.date
    time: dt.time
    time_accuracy: TimeAccuracy
    fold: Literal[0, 1] | None = None
    place: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    tz: str
    options: CaseOptions = CaseOptions()
    transit_date_utc: dt.date | None = None


class TzExpected(BaseModel):
    """Derived from the IANA tzdb, not from astrology — asserted on every run."""

    model_config = ConfigDict(frozen=True)

    utc_offset: str
    gap_shifted_minutes: int = 0
    ambiguous: bool = False


class GoldenCase(BaseModel):
    schema_version: int = SCHEMA_VERSION
    case_id: str = Field(pattern=r"^GC-\d{3}$")
    category: str
    status: CaseStatus = CaseStatus.PENDING
    source: CaseSource | None = None
    verified_by: str | None = None
    verified_on: date | None = None
    notes: str = ""
    input: CaseInput
    tz_expected: TzExpected
    expected: Expected


# --------------------------------------------------------------------------- IO


def _from_sentinel(value: Any) -> Any:
    return None if value == NEEDS_VERIFICATION else value


def _clean(mapping: dict[str, Any] | None) -> dict[str, Any]:
    return {k: _from_sentinel(v) for k, v in (mapping or {}).items()}


def parse_case(raw: dict[str, Any]) -> GoldenCase:
    version = raw.get("schema_version")
    if version != SCHEMA_VERSION:
        raise ValueError(
            f"{raw.get('case_id', '?')}: schema_version {version!r} is not the current "
            f"{SCHEMA_VERSION} — migrate the case file"
        )
    expected = raw.get("expected") or {}
    payload = {
        **raw,
        "notes": raw.get("notes") or "",
        "expected": {
            "grahas": {g: _clean(expected.get("grahas", {}).get(g)) for g in GRAHA_ORDER},
            "lagna": _clean(expected.get("lagna")),
            "dasha": {s: _clean(expected.get("dasha", {}).get(s)) for s in DASHA_SLOTS},
            "boundaries": _clean(expected.get("boundaries")),
            "transit": _clean(expected["transit"]) if expected.get("transit") else None,
        },
    }
    return GoldenCase.model_validate(payload)


def load_case(path: Path | str) -> GoldenCase:
    return parse_case(yaml.safe_load(Path(path).read_text()))


def load_all(directory: Path | str = REPO_CASES_DIR) -> list[GoldenCase]:
    paths = sorted(Path(directory).glob("GC-*.yaml"))
    if not paths:
        raise FileNotFoundError(f"no golden cases in {directory}")
    return [load_case(p) for p in paths]


_dumps = partial(json.dumps, ensure_ascii=False)


def _fmt(value: Any) -> str:
    if value is None:
        return NEEDS_VERIFICATION
    if isinstance(value, datetime):
        return _dumps(value.isoformat().replace("+00:00", "Z"))
    if isinstance(value, date | time):
        return _dumps(value.isoformat())
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, str):
        return _dumps(value)
    return repr(value)


def _block(indent: str, model: BaseModel, fields: tuple[str, ...]) -> str:
    return "\n".join(f"{indent}{f}: {_fmt(getattr(model, f))}" for f in fields)


def dump_case(case: GoldenCase) -> str:
    """Render deterministic, comment-carrying YAML (a plain yaml.dump would
    strip the guidance the reviewer relies on)."""
    grahas = "\n".join(
        f"    {name}:\n"
        + _block(
            "      ",
            case.expected.grahas[name],
            ("longitude_deg", "rashi", "nakshatra", "pada"),
        )
        for name in GRAHA_ORDER
    )
    dasha = "\n".join(
        f"    {slot}:\n" + _block("      ", case.expected.dasha[slot], ("lord", "start", "end"))
        for slot in DASHA_SLOTS
    )
    if case.expected.transit is None:
        transit = "  transit: null"
    else:
        transit = "  transit:\n" + _block(
            "    ", case.expected.transit, ("saturn_whole_sign_house", "moon_nakshatra")
        )
    return f"""schema_version: {case.schema_version}
case_id: {case.case_id}
category: {case.category}
status: {case.status.value}          # ONLY `golden verify` (a named human) may set this
source: {_fmt(case.source) if case.source else "null"}
verified_by: {_fmt(case.verified_by) if case.verified_by else "null"}
verified_on: {_fmt(case.verified_on) if case.verified_on else "null"}
notes: {_dumps(case.notes)}
input:
  date: {_fmt(case.input.date)}
  time: {_fmt(case.input.time)}
  time_accuracy: {case.input.time_accuracy.value}
  fold: {"null" if case.input.fold is None else case.input.fold}
  place: {_dumps(case.input.place)}
  lat: {case.input.lat!r}
  lon: {case.input.lon!r}
  tz: {_dumps(case.input.tz)}
  options:
    ayanamsa: {case.input.options.ayanamsa}
    node_type: {case.input.options.node_type.value}
    bhava_system: {case.input.options.bhava_system.value}
    dasha_year: {case.input.options.dasha_year.value}
    gap_policy: {case.input.options.gap_policy}
  transit_date_utc: {_fmt(case.input.transit_date_utc) if case.input.transit_date_utc else "null"}
tz_expected:             # derived from IANA tzdb — asserted every run, not astrology
  utc_offset: {_dumps(case.tz_expected.utc_offset)}
  gap_shifted_minutes: {case.tz_expected.gap_shifted_minutes}
  ambiguous: {str(case.tz_expected.ambiguous).lower()}
expected:                # fill ONLY from JHora/Drik per golden-set/cases/README.md
  grahas:
{grahas}
  lagna:
{_block("    ", case.expected.lagna, ("longitude_deg", "rashi"))}
  dasha:
{dasha}
  boundaries:
{_block("    ", case.expected.boundaries, ("moon_nakshatra_end_utc", "tithi_end_utc"))}
{transit}
"""


def save_case(case: GoldenCase, path: Path | str) -> None:
    Path(path).write_text(dump_case(case))


# ------------------------------------------------------------------ field access

_LEAF_FIELDS: dict[str, tuple[str, ...]] = {
    "grahas": ("longitude_deg", "rashi", "nakshatra", "pada"),
    "lagna": ("longitude_deg", "rashi"),
    "dasha": ("lord", "start", "end"),
    "boundaries": ("moon_nakshatra_end_utc", "tithi_end_utc"),
    "transit": ("saturn_whole_sign_house", "moon_nakshatra"),
}


def _resolve(case: GoldenCase, dotted: str) -> tuple[BaseModel, str]:
    """Map an import path onto (container model, leaf field). Only `expected`
    is reachable — verification state is never settable through import."""
    parts = dotted.split(".")
    head = parts[0]
    if head in ("grahas", "dasha"):
        if len(parts) != 3:
            raise KeyError(f"unknown field path: {dotted!r}")
        collection = getattr(case.expected, head)
        if parts[1] not in collection:
            raise KeyError(f"unknown {head[:-1]}: {parts[1]!r}")
        target, leaf = collection[parts[1]], parts[2]
    elif head in ("lagna", "boundaries", "transit"):
        if len(parts) != 2:
            raise KeyError(f"unknown field path: {dotted!r}")
        target, leaf = getattr(case.expected, head), parts[1]
        if target is None:
            raise KeyError(f"{head} is not applicable to {case.case_id}")
    else:
        raise KeyError(f"unknown field path: {dotted!r}")
    if leaf not in _LEAF_FIELDS[head]:
        raise KeyError(f"unknown field path: {dotted!r}")
    return target, leaf


def set_field(case: GoldenCase, dotted: str, raw_value: str) -> GoldenCase:
    """Return a copy with one expected value applied. Raises KeyError for
    unknown paths and ValidationError for out-of-range values."""
    updated = case.model_copy(deep=True)
    target, leaf = _resolve(updated, dotted)
    text = (raw_value or "").strip()
    if text in ("", NEEDS_VERIFICATION):
        setattr(target, leaf, None)
        return updated
    annotation = type(target).model_fields[leaf].annotation
    setattr(target, leaf, _coerce(text, annotation))
    return updated


def _coerce(text: str, annotation: Any) -> Any:
    """Pydantic handles enums/dates; datetimes need the trailing-Z form."""
    if "datetime" in str(annotation):
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    return text


def missing_required(case: GoldenCase) -> list[str]:
    """Fields a case must carry before it can be verified: all nine graha
    longitudes plus the lagna (golden-set/cases/README.md)."""
    missing = [
        f"grahas.{name}.longitude_deg"
        for name in GRAHA_ORDER
        if case.expected.grahas[name].longitude_deg is None
    ]
    if case.expected.lagna.longitude_deg is None:
        missing.append("lagna.longitude_deg")
    return missing
