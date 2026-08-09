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
