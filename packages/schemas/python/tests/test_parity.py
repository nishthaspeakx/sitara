"""Drift guards: generated Python and TypeScript artifacts must enumerate the
same members as the neutral JSON source (SPEC §34.3/§34.4/§34.6 closed sets)."""

import json
import re
from pathlib import Path

from sitara_schemas import (
    MORNING_MODULE_ORDER,
    ControlEventType,
    ErrorCode,
    MorningModule,
)

PKG = Path(__file__).resolve().parents[2]
SRC = PKG / "src"
TS_INDEX = (PKG / "typescript" / "src" / "index.ts").read_text(encoding="utf-8")


def src(name: str) -> dict:
    return json.loads((SRC / name).read_text(encoding="utf-8"))


def ts_const_array(name: str) -> list[str]:
    m = re.search(rf"export const {name} = \[(.*?)\] as const;", TS_INDEX, re.S)
    assert m, f"{name} missing from typescript/src/index.ts"
    return re.findall(r'"([^"]+)"', m.group(1))


def test_seventeen_modules_everywhere() -> None:
    source_ids = [m["id"] for m in src("modules.json")["members"]]
    assert len(source_ids) == 17
    assert [m.value for m in MORNING_MODULE_ORDER] == source_ids
    assert sorted(m.value for m in MorningModule) == sorted(source_ids)
    assert ts_const_array("MORNING_MODULES") == source_ids


def test_five_confidence_states_everywhere() -> None:
    """§5.4's five states must read the same in both languages.

    The guard exists because they did not. `sitara_api` served
    `verified_limited_birth_data` and `tradition_based_general` — §5.4's own
    wording — while the M7 component library typed `verified_limited` and
    `tradition_general`, so two of the five states the API can return could
    never have rendered a chip. Nothing failed, because no screen consumed a
    confidence state until S13; the first one to do so would simply have shown
    an unstyled chip with a raw key in it.

    Python's enum stays hand-written in `facts.py` (it lives among the Pydantic
    fact models rather than being generated), so this asserts it against the
    neutral source in both directions rather than assuming generation.
    """
    from sitara_schemas.facts import ConfidenceState

    source_ids = [m["id"] for m in src("confidence-states.json")["members"]]
    assert len(source_ids) == 5
    assert sorted(c.value for c in ConfidenceState) == sorted(source_ids)
    assert ts_const_array("CONFIDENCE_STATES") == source_ids


def test_error_codes_parity_and_namespaces() -> None:
    source = src("error-codes.json")
    source_codes = [m["code"] for m in source["members"]]
    assert sorted(c.value for c in ErrorCode) == sorted(source_codes)
    assert ts_const_array("ERROR_CODES") == source_codes
    namespaces = tuple(source["namespaces"])
    for code in source_codes:
        assert code.startswith(namespaces)


def test_ws_control_events_closed_set_parity() -> None:
    source_types = [m["type"] for m in src("ws-events.json")["members"]]
    assert len(source_types) == 15
    assert sorted(e.value for e in ControlEventType) == sorted(source_types)
    assert ts_const_array("CONTROL_EVENT_TYPES") == source_types


def test_envelope_shape() -> None:
    from sitara_schemas import ErrorEnvelope

    env = ErrorEnvelope(
        code=ErrorCode.SYS_INTERNAL,
        message_key="errors.sys.internal",
        trace_id="00000000000000000000000000000000",
        retryable=True,
    )
    assert set(env.model_dump().keys()) == {"code", "message_key", "trace_id", "retryable"}


# ---------------------------------------------------------------------------
# §28.2 — the Today payload
# ---------------------------------------------------------------------------


def test_today_enums_agree_across_both_languages() -> None:
    """The five closed sets §28.2's payload carries.

    Same guard, same reason as the confidence states above: these ids are the
    WIRE format. `sitara_api` serves them and the Today screen switches on them,
    so a set that reads `verified_core_cards` on one side and `core_cards` on
    the other is a degraded morning that renders as a normal one.
    """
    import sitara_schemas.today as today_mod

    source = src("today.json")["enums"]
    assert source, "today.json declares no enums"
    for spec in source.values():
        ids = [m["id"] for m in spec["members"]]
        enum = getattr(today_mod, spec["enum_name"])
        assert sorted(m.value for m in enum) == sorted(ids), spec["enum_name"]
        assert ts_const_array(spec["const_name"]) == ids, spec["const_name"]


def test_today_payload_fields_agree_across_both_languages() -> None:
    """A field present on one side of the wire and absent on the other is a
    field the screen reads as `undefined` — silently, and only in production."""
    import sitara_schemas.today as today_mod

    for name, shape in src("today.json")["shapes"].items():
        declared = [f["name"] for f in shape["fields"]]
        model = getattr(today_mod, name)
        assert list(model.model_fields) == declared, f"{name} (python)"

        m = re.search(rf"export interface {name} \{{(.*?)\n\}}", TS_INDEX, re.S)
        assert m, f"{name} missing from typescript/src/index.ts"
        assert re.findall(r"^\s+(\w+):", m.group(1), re.M) == declared, f"{name} (ts)"


def test_today_payload_cannot_carry_a_fact_id() -> None:
    """§30.4: "fact-IDs remain internal (logs/admin) and never render to users".

    The guarantee is structural on the component side — `TrustSheet` has no prop
    that could hold one — and this keeps the wire honest to the same standard.
    A `fact_ids` field would make leaking them a matter of remembering not to.
    """
    for name, shape in src("today.json")["shapes"].items():
        for field in shape["fields"]:
            assert "fact_id" not in field["name"], f"{name}.{field['name']}"


def test_time_band_thresholds_agree_across_both_languages() -> None:
    """§28.2's "the whole tab transforms after 20:00" is ONE threshold.

    The API composes Tara's line for the band and the client renders the night
    takeover, so the boundary is read on both sides. Two hand-written 20:00s is
    how a screen goes to dusk an hour after the sentence on it did.
    """
    from sitara_schemas.today import TIME_BAND_STARTS, TimeBand, time_band

    spec = src("today.json")["time_bands"]
    ids = [m["id"] for m in spec["members"]]
    assert sorted(b.value for b in TimeBand) == sorted(ids)
    assert ts_const_array(spec["const_name"]) == ids

    # Latest-first, so a lookup is "the first band this time has reached".
    declared = {m["id"]: m["starts_at"] for m in spec["members"]}
    assert [(b.value, s) for b, s in TIME_BAND_STARTS] == [
        (i, declared[i]) for i in reversed(ids)
    ]
    ts_pairs = re.findall(r'\["(\w+)", "([\d:]+)"\]', TS_INDEX)
    assert ts_pairs == [(i, declared[i]) for i in reversed(ids)]

    # Each band's own first minute, and the minute before it.
    for index, member in enumerate(spec["members"]):
        assert time_band(member["starts_at"]).value == member["id"]
        if index:
            hh, mm = (int(p) for p in member["starts_at"].split(":"))
            before = f"{hh - 1:02d}:59" if mm == 0 else f"{hh:02d}:{mm - 1:02d}"
            assert time_band(before).value == spec["members"][index - 1]["id"]
