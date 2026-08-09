#!/usr/bin/env python3
"""Generate Python (Pydantic v2) and TypeScript artifacts from the neutral JSON sources.

One source of truth (packages/schemas/src/*.json) -> two targets:
  python/sitara_schemas/   (consumed by services/*)
  typescript/src/index.ts  (consumed by apps/*)

Deterministic output: run twice -> identical bytes. CI regenerates and fails on drift.
Stdlib only — no dependencies. Spec: §34.3 (modules), §34.4 (errors), §34.6 (WS protocol).
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
PY_OUT = ROOT / "python" / "sitara_schemas"
TS_OUT = ROOT / "typescript" / "src"

HEADER = "GENERATED FILE — do not edit. Source: packages/schemas/src/*.json (run scripts/generate.py)."


def load(name: str) -> dict:
    return json.loads((SRC / name).read_text(encoding="utf-8"))


def py_ident(member_id: str) -> str:
    """`session.ready` -> SESSION_READY ; `energy_of_day` -> ENERGY_OF_DAY."""
    return member_id.replace(".", "_").replace("-", "_").upper()


# ------------------------------------------------------------- shape types
#
# The §28.2 payload is the first source here that declares STRUCTURE and not
# only a closed set, so it needs a type mapper. The vocabulary is deliberately
# tiny — scalars, an optional marker, a list marker, and a reference to an enum
# or another shape. Anything a richer type system would buy is a thing the wire
# should not be carrying.

_PY_SCALARS = {"string": "str", "boolean": "bool", "integer": "int"}
_TS_SCALARS = {"string": "string", "boolean": "boolean", "integer": "number"}


def _split_type(declared: str) -> tuple[str, bool, bool]:
    """`"TodayModule[]"` -> ("TodayModule", is_list=True, optional=False)."""
    optional = declared.endswith("?")
    base = declared[:-1] if optional else declared
    is_list = base.endswith("[]")
    if is_list:
        base = base[:-2]
    return base, is_list, optional


def py_type(declared: str) -> str:
    base, is_list, optional = _split_type(declared)
    inner = _PY_SCALARS.get(base, base)
    if is_list:
        inner = f"tuple[{inner}, ...]"
    return f"{inner} | None" if optional else inner


def ts_type(declared: str) -> str:
    base, is_list, optional = _split_type(declared)
    inner = _TS_SCALARS.get(base, base)
    if is_list:
        inner = f"{inner}[]"
    return f"{inner} | null" if optional else inner


# ---------------------------------------------------------------- python

def gen_python(modules: dict, codes: dict, envelope: dict, ws: dict, today: dict) -> None:
    PY_OUT.mkdir(parents=True, exist_ok=True)

    # modules.py
    lines = [
        f'"""{HEADER}"""',
        "",
        "from enum import StrEnum",
        "",
        "",
        "class MorningModule(StrEnum):",
        '    """SPEC §7.1 / §34.3 — the canonical 17 morning modules (closed set).',
        "",
        "    The ranking engine emits ONLY these IDs.",
        '    """',
        "",
    ]
    for m in modules["members"]:
        lines.append(f'    {py_ident(m["id"])} = "{m["id"]}"')
    lines += [
        "",
        "",
        "MORNING_MODULE_ORDER: tuple[MorningModule, ...] = (",
    ]
    for m in modules["members"]:
        lines.append(f"    MorningModule.{py_ident(m['id'])},")
    lines += [")", ""]
    (PY_OUT / "modules.py").write_text("\n".join(lines), encoding="utf-8")

    # errors.py
    lines = [
        f'"""{HEADER}"""',
        "",
        "from enum import StrEnum",
        "",
        "from pydantic import BaseModel, ConfigDict",
        "",
        "",
        "class ErrorCode(StrEnum):",
        '    """SPEC §6.3 / §34.4 — namespaced error codes (closed namespaces:',
        "    AUTH_/ASTRO_/VOICE_/PAY_/SAFE_/SYS_). New codes are PR-reviewed.",
        '    """',
        "",
    ]
    for m in codes["members"]:
        lines.append(f'    {m["code"]} = "{m["code"]}"')
    lines += [
        "",
        "",
        "HTTP_STATUS: dict[ErrorCode, int] = {",
    ]
    for m in codes["members"]:
        lines.append(f"    ErrorCode.{m['code']}: {m['http_status']},")
    lines += [
        "}",
        "",
        "DEFAULT_RETRYABLE: dict[ErrorCode, bool] = {",
    ]
    for m in codes["members"]:
        lines.append(f"    ErrorCode.{m['code']}: {str(m['retryable'])},")
    lines += [
        "}",
        "",
        "",
        "class ErrorEnvelope(BaseModel):",
        '    """SPEC §34.4 — the ONE canonical error envelope. No module invents its own."""',
        "",
        '    model_config = ConfigDict(frozen=True)',
        "",
        "    code: ErrorCode",
        "    message_key: str",
        "    trace_id: str",
        "    retryable: bool",
        "",
    ]
    (PY_OUT / "errors.py").write_text("\n".join(lines), encoding="utf-8")

    # ws_events.py
    bf = ws["binary_frame"]
    lines = [
        f'"""{HEADER}"""',
        "",
        "from enum import StrEnum",
        "from typing import Any",
        "",
        "from pydantic import BaseModel, ConfigDict",
        "",
        "",
        "class ControlEventType(StrEnum):",
        '    """SPEC §34.6 — the CLOSED control-event type set for the voice/call WS protocol."""',
        "",
    ]
    for m in ws["members"]:
        lines.append(f'    {py_ident(m["type"])} = "{m["type"]}"')
    lines += [
        "",
        "",
        "class ControlEvent(BaseModel):",
        '    """SPEC §34.6 — JSON text-frame control event {type, seq, ts, payload}."""',
        "",
        "    model_config = ConfigDict(frozen=True)",
        "",
        "    type: ControlEventType",
        "    seq: int",
        "    ts: float",
        "    payload: dict[str, Any]",
        "",
        "",
        "# Binary frame contract (SPEC §34.6): 16kHz mono PCM, 8-byte header.",
        f'BINARY_AUDIO_FORMAT = "{bf["audio_format"]}"',
        f"BINARY_SAMPLE_RATE_HZ = {bf['sample_rate_hz']}",
        f"BINARY_CHANNELS = {bf['channels']}",
        f"BINARY_HEADER_BYTES = {bf['header_bytes']}",
        f"BINARY_HEADER_SEQ_BYTES = {bf['header_layout'][0]['bytes']}",
        f"BINARY_HEADER_FLAGS_BYTES = {bf['header_layout'][1]['bytes']}",
        "",
        f"HEARTBEAT_INTERVAL_S = {ws['heartbeat_interval_s']}",
        f"REAP_AFTER_SILENCE_S = {ws['reap_after_silence_s']}",
        f"RESUME_WINDOW_S = {ws['resume_window_s']}",
        "",
    ]
    (PY_OUT / "ws_events.py").write_text("\n".join(lines), encoding="utf-8")

    # today.py
    lines = [
        f'"""{HEADER}',
        "",
        "SPEC §28.2 — the Today payload and the closed sets it carries.",
        "",
        "`sitara_api.daily_guidance.types` imports Density, Tier, BriefStatus and",
        "BriefDegradeReason FROM HERE rather than declaring its own. Both sides of",
        "the wire need them, and a second declaration is how the two drift — the",
        "same reason §34.3's MorningModule was never copied into the service.",
        '"""',
        "",
        "from enum import StrEnum",
        "",
        "from pydantic import BaseModel, ConfigDict",
        "",
        "from sitara_schemas.facts import ConfidenceState",
        "from sitara_schemas.modules import MorningModule",
        "",
        "__all__ = [",
    ]
    exported = [
        *today["enums"],
        *today["shapes"],
        today["time_bands"]["enum_name"],
        "TIME_BAND_STARTS",
        "time_band",
    ]
    for name in sorted(exported):
        lines.append(f'    "{name}",')
    lines += ["]", ""]

    for enum in today["enums"].values():
        lines += ["", f"class {enum['enum_name']}(StrEnum):", f'    """{enum["$comment"]}"""', ""]
        for m in enum["members"]:
            lines.append(f'    {py_ident(m["id"])} = "{m["id"]}"')
        lines.append("")

    bands = today["time_bands"]
    lines += ["", f"class {bands['enum_name']}(StrEnum):", f'    """{bands["$comment"]}"""', ""]
    for m in bands["members"]:
        lines.append(f'    {py_ident(m["id"])} = "{m["id"]}"')
    lines += [
        "",
        "",
        "#: Each band's first minute, local. Ordered latest-first so a lookup is",
        "#: 'the first band whose start this time has reached'.",
        f"TIME_BAND_STARTS: tuple[tuple[{bands['enum_name']}, str], ...] = (",
    ]
    for m in reversed(bands["members"]):
        lines.append(f'    ({bands["enum_name"]}.{py_ident(m["id"])}, "{m["starts_at"]}"),')
    lines += [
        ")",
        "",
        "",
        f"def time_band(local_time: str) -> {bands['enum_name']}:",
        '    """§28.2\'s band for a zero-padded local "HH:MM". Never a UTC time."""',
        "    for band, starts_at in TIME_BAND_STARTS:",
        "        if local_time >= starts_at:",
        "            return band",
        f"    return {bands['enum_name']}.{py_ident(bands['members'][0]['id'])}",
        "",
    ]

    for name, shape in today["shapes"].items():
        lines += [
            "",
            f"class {name}(BaseModel):",
            f'    """{shape["$comment"]}"""',
            "",
            "    model_config = ConfigDict(frozen=True)",
            "",
        ]
        for f in shape["fields"]:
            default = " = None" if f["type"].endswith("?") else ""
            lines.append(f'    {f["name"]}: {py_type(f["type"])}{default}')
        lines.append("")
    (PY_OUT / "today.py").write_text("\n".join(lines), encoding="utf-8")

    # __init__.py
    lines = [
        f'"""{HEADER}',
        "",
        "sitara_schemas — the shared frozen contracts (SPEC §34.3/§34.4/§34.6).",
        '"""',
        "",
        "from sitara_schemas.errors import (",
        "    DEFAULT_RETRYABLE,",
        "    HTTP_STATUS,",
        "    ErrorCode,",
        "    ErrorEnvelope,",
        ")",
        "from sitara_schemas.modules import MORNING_MODULE_ORDER, MorningModule",
        "from sitara_schemas.ws_events import (",
        "    BINARY_AUDIO_FORMAT,",
        "    BINARY_CHANNELS,",
        "    BINARY_HEADER_BYTES,",
        "    BINARY_HEADER_FLAGS_BYTES,",
        "    BINARY_HEADER_SEQ_BYTES,",
        "    BINARY_SAMPLE_RATE_HZ,",
        "    HEARTBEAT_INTERVAL_S,",
        "    REAP_AFTER_SILENCE_S,",
        "    RESUME_WINDOW_S,",
        "    ControlEvent,",
        "    ControlEventType,",
        ")",
        "",
        "__all__ = [",
        '    "BINARY_AUDIO_FORMAT",',
        '    "BINARY_CHANNELS",',
        '    "BINARY_HEADER_BYTES",',
        '    "BINARY_HEADER_FLAGS_BYTES",',
        '    "BINARY_HEADER_SEQ_BYTES",',
        '    "BINARY_SAMPLE_RATE_HZ",',
        '    "DEFAULT_RETRYABLE",',
        '    "HEARTBEAT_INTERVAL_S",',
        '    "HTTP_STATUS",',
        '    "MORNING_MODULE_ORDER",',
        '    "REAP_AFTER_SILENCE_S",',
        '    "RESUME_WINDOW_S",',
        '    "ControlEvent",',
        '    "ControlEventType",',
        '    "ErrorCode",',
        '    "ErrorEnvelope",',
        '    "MorningModule",',
        "]",
        "",
    ]
    (PY_OUT / "__init__.py").write_text("\n".join(lines), encoding="utf-8")


# ------------------------------------------------------------ typescript

def gen_typescript(
    modules: dict, codes: dict, envelope: dict, ws: dict, confidence: dict, today: dict
) -> None:
    TS_OUT.mkdir(parents=True, exist_ok=True)
    bf = ws["binary_frame"]

    confidence_ids = ", ".join(f'"{m["id"]}"' for m in confidence["members"])
    module_ids = ", ".join(f'"{m["id"]}"' for m in modules["members"])
    code_ids = ", ".join(f'"{m["code"]}"' for m in codes["members"])
    event_ids = ", ".join(f'"{m["type"]}"' for m in ws["members"])

    lines = [
        f"// {HEADER}",
        "",
        "// ---------------------------------------------------------------------------",
        "// SPEC §7.1 / §34.3 — the canonical 17 morning modules (closed set).",
        "// The ranking engine emits ONLY these IDs.",
        "// ---------------------------------------------------------------------------",
        f"export const MORNING_MODULES = [{module_ids}] as const;",
        "export type MorningModule = (typeof MORNING_MODULES)[number];",
        "",
        "// ---------------------------------------------------------------------------",
        "// SPEC §5.4 / §34.7 — the five user-visible confidence states (closed set).",
        "// These IDs are the WIRE format: sitara-api serves them verbatim and",
        "// ConfidenceChip renders them. The two drifted once (M8) — hence one source.",
        "// ---------------------------------------------------------------------------",
        f"export const CONFIDENCE_STATES = [{confidence_ids}] as const;",
        "export type ConfidenceState = (typeof CONFIDENCE_STATES)[number];",
        "",
        "// ---------------------------------------------------------------------------",
        "// SPEC §6.3 / §34.4 — namespaced error codes + the ONE canonical envelope.",
        "// ---------------------------------------------------------------------------",
        f"export const ERROR_CODES = [{code_ids}] as const;",
        "export type ErrorCode = (typeof ERROR_CODES)[number];",
        "",
        "export const ERROR_HTTP_STATUS: Record<ErrorCode, number> = {",
    ]
    for m in codes["members"]:
        lines.append(f'  {m["code"]}: {m["http_status"]},')
    lines += [
        "};",
        "",
        "export const ERROR_DEFAULT_RETRYABLE: Record<ErrorCode, boolean> = {",
    ]
    for m in codes["members"]:
        lines.append(f'  {m["code"]}: {"true" if m["retryable"] else "false"},')
    lines += [
        "};",
        "",
        "/** SPEC §34.4 — the ONE canonical error envelope. No module invents its own. */",
        "export interface ErrorEnvelope {",
        "  code: ErrorCode;",
        "  message_key: string;",
        "  trace_id: string;",
        "  retryable: boolean;",
        "}",
        "",
        "// ---------------------------------------------------------------------------",
        "// SPEC §34.6 — voice/call WebSocket wire protocol (closed control-event set).",
        "// Binary frames: 16kHz mono PCM, 8-byte header (4-byte seq + 4-byte flags).",
        "// ---------------------------------------------------------------------------",
        f"export const CONTROL_EVENT_TYPES = [{event_ids}] as const;",
        "export type ControlEventType = (typeof CONTROL_EVENT_TYPES)[number];",
        "",
        "/** SPEC §34.6 — JSON text-frame control event. Server acks by seq. */",
        "export interface ControlEvent {",
        "  type: ControlEventType;",
        "  seq: number;",
        "  ts: number;",
        "  payload: Record<string, unknown>;",
        "}",
        "",
        f'export const BINARY_AUDIO_FORMAT = "{bf["audio_format"]}" as const;',
        f"export const BINARY_SAMPLE_RATE_HZ = {bf['sample_rate_hz']} as const;",
        f"export const BINARY_CHANNELS = {bf['channels']} as const;",
        f"export const BINARY_HEADER_BYTES = {bf['header_bytes']} as const;",
        f"export const BINARY_HEADER_SEQ_BYTES = {bf['header_layout'][0]['bytes']} as const;",
        f"export const BINARY_HEADER_FLAGS_BYTES = {bf['header_layout'][1]['bytes']} as const;",
        "",
        f"export const HEARTBEAT_INTERVAL_S = {ws['heartbeat_interval_s']} as const;",
        f"export const REAP_AFTER_SILENCE_S = {ws['reap_after_silence_s']} as const;",
        f"export const RESUME_WINDOW_S = {ws['resume_window_s']} as const;",
        "",
        "// ---------------------------------------------------------------------------",
        "// SPEC §28.2 — the Today payload and the closed sets it carries.",
        "// `variant` is deliberately absent: §32.1's precedence is a RULE over this",
        "// state, evaluated in apps/web/src/lib/today-variant.ts, not a server value.",
        "// ---------------------------------------------------------------------------",
    ]
    for enum in today["enums"].values():
        name = enum["enum_name"]
        ids = ", ".join(f'"{m["id"]}"' for m in enum["members"])
        # The plural is DECLARED, not inflected. `DENSITYS` and `BRIEF_STATUSS`
        # are what a rule produces; naming is not a thing to be clever about in
        # generated code someone has to read.
        const = enum["const_name"]
        lines += [
            f"export const {const} = [{ids}] as const;",
            f"export type {name} = (typeof {const})[number];",
        ]
    bands = today["time_bands"]
    band_ids = ", ".join(f'"{m["id"]}"' for m in bands["members"])
    lines += [
        f"export const {bands['const_name']} = [{band_ids}] as const;",
        f"export type {bands['enum_name']} = (typeof {bands['const_name']})[number];",
        "",
        f"/** {bands['$comment']} */",
        f"export const TIME_BAND_STARTS: ReadonlyArray<readonly [{bands['enum_name']}, string]> = [",
    ]
    for m in reversed(bands["members"]):
        lines.append(f'  ["{m["id"]}", "{m["starts_at"]}"],')
    lines += [
        "];",
        "",
        '/** §28.2\'s band for a zero-padded local "HH:MM". Never a UTC time. */',
        f"export function timeBand(localTime: string): {bands['enum_name']} {{",
        "  for (const [band, startsAt] of TIME_BAND_STARTS) {",
        "    if (localTime >= startsAt) return band;",
        "  }",
        f'  return "{bands["members"][0]["id"]}";',
        "}",
        "",
    ]
    for name, shape in today["shapes"].items():
        lines += [f"/** {shape['$comment']} */", f"export interface {name} {{"]
        for f in shape["fields"]:
            lines.append(f'  {f["name"]}: {ts_type(f["type"])};')
        lines += ["}", ""]
    (TS_OUT / "index.ts").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    modules = load("modules.json")
    codes = load("error-codes.json")
    envelope = load("error-envelope.json")
    ws = load("ws-events.json")
    confidence = load("confidence-states.json")
    today = load("today.json")

    assert len(modules["members"]) == 17, "SPEC §34.3: exactly 17 morning modules"
    assert len(confidence["members"]) == 5, "SPEC §5.4: exactly 5 confidence states"
    assert len(ws["members"]) == 15, "SPEC §34.6: closed set of 15 control events"
    for m in codes["members"]:
        assert any(m["code"].startswith(ns) for ns in codes["namespaces"]), (
            f"error code {m['code']} outside closed namespaces"
        )

    gen_python(modules, codes, envelope, ws, today)
    gen_typescript(modules, codes, envelope, ws, confidence, today)
    print("generated: python/sitara_schemas/{__init__,modules,errors,ws_events,today}.py")
    print("generated: typescript/src/index.ts")


if __name__ == "__main__":
    main()
