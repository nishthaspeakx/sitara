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


#: `const:user` -> a field PINNED to one value.
#:
#: The fifth and (deliberately) last member of the type vocabulary, added in M9
#: for `PartialCaptionPayload.role`. It earns its place by making a rule
#: unrepresentable rather than merely documented: §34.6 forbids a partial
#: caption of Tara's words, and through M8 that held only because no code wrote
#: the frame. A `ChatRole` there would re-open it the moment M9 wrote one. A
#: constant closes it in the type — which is the same move `PriceCard` makes by
#: having no countdown prop and `TrustSheet` by having no fact-id prop.
_CONST_PREFIX = "const:"


def py_const(value: object) -> str:
    """A JSON constant as Python source.

    A list becomes a TUPLE. §32.9's `ENTITLEMENT_WARNING_MINUTES` is the first
    constant here that is a sequence, and a mutable module-level list in a
    package whose whole job is being the one declaration of a shared set is a
    set anyone can quietly change at runtime. TypeScript already gets `as const`
    on the same value; this is the Python half of the same guarantee.
    """
    if isinstance(value, list):
        inner = ", ".join(py_const(v) for v in value)
        return f"({inner},)" if len(value) == 1 else f"({inner})"
    return repr(value)


def py_type(declared: str) -> str:
    base, is_list, optional = _split_type(declared)
    if base.startswith(_CONST_PREFIX):
        return f'Literal["{base[len(_CONST_PREFIX):]}"]'
    inner = _PY_SCALARS.get(base, base)
    if is_list:
        inner = f"tuple[{inner}, ...]"
    return f"{inner} | None" if optional else inner


def ts_type(declared: str) -> str:
    base, is_list, optional = _split_type(declared)
    if base.startswith(_CONST_PREFIX):
        return f'"{base[len(_CONST_PREFIX):]}"'
    inner = _TS_SCALARS.get(base, base)
    if is_list:
        inner = f"{inner}[]"
    return f"{inner} | null" if optional else inner


# ------------------------------------------------------- shared emitters
#
# `today.json` was the only source declaring structure, so its enum and shape
# emitters lived inline in `gen_python`/`gen_typescript`. §25.4's chat payloads
# and §34.6's now-typed control-event payloads are the second and third, and a
# third copy of "walk fields, map types, write a class" is how the three drift
# in exactly the way every closed set in this package exists to prevent.


def py_enum(spec: dict) -> list[str]:
    """A StrEnum from a `{enum_name, members:[{id}]}` block."""
    lines = ["", f"class {spec['enum_name']}(StrEnum):", f'    """{spec["$comment"]}"""', ""]
    for m in spec["members"]:
        lines.append(f'    {py_ident(m["id"])} = "{m["id"]}"')
    lines.append("")
    return lines


def py_shape(name: str, shape: dict) -> list[str]:
    lines = [
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
    return lines


def ts_enum(spec: dict) -> list[str]:
    ids = ", ".join(f'"{m["id"]}"' for m in spec["members"])
    return [
        f"/** {spec['$comment']} */",
        f"export const {spec['const_name']} = [{ids}] as const;",
        f"export type {spec['enum_name']} = (typeof {spec['const_name']})[number];",
        "",
    ]


def ts_shape(name: str, shape: dict) -> list[str]:
    lines = [f"/** {shape['$comment']} */", f"export interface {name} {{"]
    for f in shape["fields"]:
        lines.append(f'  {f["name"]}: {ts_type(f["type"])};')
    lines += ["}", ""]
    return lines


def ordinals(spec: dict) -> dict[str, int]:
    """§4.3 numbers its presence states and §32.4 numbers its memory types. The
    ordinal is documentation and a threshold operand — never the wire format."""
    return {m["id"]: m["ordinal"] for m in spec["members"] if "ordinal" in m}


# ---------------------------------------------------------------- python

def gen_python(
    modules: dict,
    codes: dict,
    envelope: dict,
    ws: dict,
    today: dict,
    presence: dict,
    memory_types: dict,
    chat: dict,
    voice: dict,
) -> None:
    PY_OUT.mkdir(parents=True, exist_ok=True)

    # presence.py
    lines = [
        f'"""{HEADER}',
        "",
        "SPEC §4.3 — Tara's twelve presence states.",
        "",
        "`sitara_api.chat_orchestration` and `apps/web`'s component library both",
        "import from here. They each held their own twelve until M8-P10, and the",
        "two disagreed on five of them by name AND by position — see the source",
        "JSON's comment. The ID is the wire format; ORDINAL is §4.3's numbering.",
        '"""',
        "",
        "from enum import StrEnum",
        "",
    ]
    lines += py_enum(presence)
    lines += [
        "",
        "#: §4.3's own numbering. Kept so a trace can record the number the spec",
        "#: uses and a reader can check this file against the spec line. NOT the",
        "#: wire format: a positional contract is what drifted in the first place.",
        f"PRESENCE_ORDINAL: dict[{presence['enum_name']}, int] = {{",
    ]
    for member_id, ordinal in ordinals(presence).items():
        lines.append(f"    {presence['enum_name']}.{py_ident(member_id)}: {ordinal},")
    lines += [
        "}",
        "",
        "#: §4.3's ● marks — the states that have a cinemagraph loop. The delivered",
        "#: kit is stills only (cinemagraphs are deferred post-beta, recorded in",
        "#: apps/web's TARA_MOTION_STATUS); this is what §4.3 SPECIFIES, not what",
        "#: has shipped, and the two are checked against each other there.",
        f"PRESENCE_CINEMAGRAPH: frozenset[{presence['enum_name']}] = frozenset({{",
    ]
    for m in presence["members"]:
        if m.get("cinemagraph"):
            lines.append(f"    {presence['enum_name']}.{py_ident(m['id'])},")
    lines += ["})", ""]
    (PY_OUT / "presence.py").write_text("\n".join(lines), encoding="utf-8")

    # memory_types.py
    lines = [
        f'"""{HEADER}',
        "",
        "SPEC §32.4 — the eleven memory types.",
        "",
        "The closed set of IDs only. The RULES attached to each type — consent,",
        "visibility gates, decay half-lives — belong to the memory module (§6.3)",
        "and stay in `sitara_api.memory.taxonomy`, which imports its enum from",
        "here rather than declaring a second one.",
        '"""',
        "",
        "from enum import StrEnum",
        "",
    ]
    lines += py_enum(memory_types)
    lines += [
        "",
        "#: §32.4's numbering, so the vault renders 1–11 as the spec numbers them.",
        f"MEMORY_TYPE_ORDER: tuple[{memory_types['enum_name']}, ...] = (",
    ]
    for m in memory_types["members"]:
        lines.append(f"    {memory_types['enum_name']}.{py_ident(m['id'])},")
    lines += [")", ""]
    (PY_OUT / "memory_types.py").write_text("\n".join(lines), encoding="utf-8")

    # chat.py
    lines = [
        f'"""{HEADER}',
        "",
        "SPEC §25.4 / §30.4 — one chat turn, as it crosses the wire.",
        "",
        "Served identically by `POST /v1/chat/turn` and by the §34.6 socket's",
        "`captions.final`, because a turn that renders one way over HTTP and",
        "another over the socket is two chat screens wearing one name.",
        '"""',
        "",
        "from enum import StrEnum",
        "",
        "from pydantic import BaseModel, ConfigDict",
        "",
        "from sitara_schemas.facts import ConfidenceState",
        "from sitara_schemas.memory_types import MemoryType",
        "from sitara_schemas.presence import PresenceState",
        "",
        "__all__ = [",
    ]
    chat_exports = [
        *(e["enum_name"] for e in chat["enums"].values()),
        *chat["shapes"],
        *chat["constants"],
        "SAFETY_LEVEL_ORDINAL",
    ]
    for name in sorted(chat_exports):
        lines.append(f'    "{name}",')
    lines += ["]", ""]
    for enum in chat["enums"].values():
        lines += py_enum(enum)
    safety = chat["enums"]["safety_level"]
    lines += [
        "",
        "#: §9's ladder as numbers, for the ONE comparison the client and the",
        "#: server both make: is this L3 or above?",
        f"SAFETY_LEVEL_ORDINAL: dict[{safety['enum_name']}, int] = {{",
    ]
    for member_id, ordinal in ordinals(safety).items():
        lines.append(f"    {safety['enum_name']}.{py_ident(member_id)}: {ordinal},")
    lines += ["}", ""]
    for name, const in chat["constants"].items():
        lines += ["", f"#: {const['$comment']}", f"{name} = {const['value']}"]
    lines.append("")
    for name, shape in chat["shapes"].items():
        lines += py_shape(name, shape)
    (PY_OUT / "chat.py").write_text("\n".join(lines), encoding="utf-8")

    # voice.py
    lines = [
        f'"""{HEADER}',
        "",
        "SPEC §33.1 / §6.4 / §25.4 — the vocabulary of a voice note.",
        "",
        "`sitara_api.chat_orchestration.store` writes `transcript_status` and",
        "`playback_policy` onto every message row; `apps/web`'s VoiceNoteBubble",
        "renders them. They held different sets until M9 — see the source JSON.",
        '"""',
        "",
        "from enum import StrEnum",
        "",
        "__all__ = [",
    ]
    voice_exports = [
        *(e["enum_name"] for e in voice["enums"].values()),
        *(e["const_name"] for e in voice["enums"].values()),
        *voice["constants"],
    ]
    for name in sorted(voice_exports):
        lines.append(f'    "{name}",')
    lines += ["]", ""]
    for enum in voice["enums"].values():
        lines += py_enum(enum)
        # The tuple form exists so a test, a validator or a Mongo `enum:` clause
        # can iterate the set without importing the class — the same service
        # MEMORY_TYPE_ORDER does for §32.4.
        lines += [
            "",
            f"{enum['const_name']}: tuple[{enum['enum_name']}, ...] = (",
            *(f"    {enum['enum_name']}.{py_ident(m['id'])}," for m in enum["members"]),
            ")",
            "",
        ]
    for name, const in voice["constants"].items():
        lines += ["", f"#: {const['$comment']}", f"{name} = {py_const(const['value'])}"]
    lines.append("")
    (PY_OUT / "voice.py").write_text("\n".join(lines), encoding="utf-8")

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
        "from typing import Any, Literal",
        "",
        "from pydantic import BaseModel, ConfigDict",
        "",
        "from sitara_schemas.chat import ChatRole, ChatTurn",
        "from sitara_schemas.presence import PresenceState",
        "from sitara_schemas.voice import (",
        "    BargeInReason,",
        "    PlaybackPolicy,",
        "    TranscriptStatus,",
        "    VadState,",
        ")",
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
        '    """SPEC §34.6 — JSON text-frame control event {type, seq, ts, ack, payload}."""',
        "",
        "    model_config = ConfigDict(frozen=True)",
        "",
        "    type: ControlEventType",
        "    seq: int",
        "    ts: float",
        "    ack: int | None = None",
        "    payload: dict[str, Any]",
        "",
    ]
    lines += [
        "",
        "# --------------------------------------------------------------------",
        "# Payload shapes — the text chat (S18), the voice notes (M9), the live",
        "# call (M10). All fifteen members are now typed.",
        "#",
        "# §34.6 says payloads are 'typed per event in M9'. The rule that actually",
        "# held is narrower: a payload is typed by the milestone that starts",
        "# EMITTING it, because typing an event nobody produces is a guess with a",
        "# schema around it. S18 typed the text-chat members, M9 typed vad.state",
        "# and tts.*, and M10 types the last two — `barge_in` (§25.3's server-side",
        "# VAD ducking) and `entitlement.warning` (§7.3's minute pool) — because",
        "# M10 is the milestone that sends them.",
        "#",
        "# The set of MEMBERS has not moved and must not: fifteen, closed, §31.3",
        "# change control. A live call speaking the same fifteen as a typed chat",
        "# is what §34.6 claimed and what M10 is the test of.",
        "# --------------------------------------------------------------------",
    ]
    for name, shape in ws["payload_shapes"].items():
        lines += py_shape(name, shape)
    lines += [
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
        lines += py_enum(enum)

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
        lines += py_shape(name, shape)
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
        "from sitara_schemas.chat import (",
        "    SAFETY_LEVEL_ORDINAL,",
        "    SAFETY_TAKEOVER_FROM_ORDINAL,",
        "    ChatCitation,",
        "    ChatRole,",
        "    ChatTrust,",
        "    ChatTurn,",
        "    MemoryChipOffer,",
        "    SafetyLevel,",
        "    SourceState,",
        ")",
        "from sitara_schemas.memory_types import MEMORY_TYPE_ORDER, MemoryType",
        "from sitara_schemas.modules import MORNING_MODULE_ORDER, MorningModule",
        "from sitara_schemas.presence import (",
        "    PRESENCE_CINEMAGRAPH,",
        "    PRESENCE_ORDINAL,",
        "    PresenceState,",
        ")",
        "from sitara_schemas.voice import (",
        "    BARGE_IN_REASONS,",
        "    ENTITLEMENT_WARNING_MINUTES,",
        "    HOLDING_PHRASE_AFTER_MS,",
        "    MAX_NOTE_DURATION_MS,",
        "    PLAYBACK_POLICIES,",
        "    SOURCE_AUDIO_RETENTION_DAYS,",
        "    TRANSCRIPT_STATUSES,",
        "    VAD_STATES,",
        "    BargeInReason,",
        "    PlaybackPolicy,",
        "    TranscriptStatus,",
        "    VadState,",
        ")",
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
        "    BargeInPayload,",
        "    ControlEvent,",
        "    ControlEventType,",
        "    EntitlementWarningPayload,",
        "    HandoffToTextPayload,",
        "    PartialCaptionPayload,",
        "    PresenceStatePayload,",
        "    ResumeOfferPayload,",
        "    SessionReadyPayload,",
        "    SessionStartPayload,",
        "    TaraTurnPayload,",
        "    TtsChunkMetaPayload,",
        "    TtsEndPayload,",
        "    TtsStartPayload,",
        "    UserTurnPayload,",
        "    VadStatePayload,",
        ")",
        "",
        "__all__ = [",
    ]
    for name in sorted(
        [
            "BARGE_IN_REASONS",
            "BINARY_AUDIO_FORMAT",
            "BINARY_CHANNELS",
            "BINARY_HEADER_BYTES",
            "BINARY_HEADER_FLAGS_BYTES",
            "BINARY_HEADER_SEQ_BYTES",
            "BINARY_SAMPLE_RATE_HZ",
            "DEFAULT_RETRYABLE",
            "ENTITLEMENT_WARNING_MINUTES",
            "HEARTBEAT_INTERVAL_S",
            "HOLDING_PHRASE_AFTER_MS",
            "HTTP_STATUS",
            "MAX_NOTE_DURATION_MS",
            "MEMORY_TYPE_ORDER",
            "MORNING_MODULE_ORDER",
            "PLAYBACK_POLICIES",
            "PRESENCE_CINEMAGRAPH",
            "PRESENCE_ORDINAL",
            "REAP_AFTER_SILENCE_S",
            "RESUME_WINDOW_S",
            "SAFETY_LEVEL_ORDINAL",
            "SAFETY_TAKEOVER_FROM_ORDINAL",
            "SOURCE_AUDIO_RETENTION_DAYS",
            "TRANSCRIPT_STATUSES",
            "VAD_STATES",
            "BargeInPayload",
            "BargeInReason",
            "ChatCitation",
            "ChatRole",
            "ChatTrust",
            "ChatTurn",
            "ControlEvent",
            "ControlEventType",
            "EntitlementWarningPayload",
            "ErrorCode",
            "ErrorEnvelope",
            "HandoffToTextPayload",
            "MemoryChipOffer",
            "MemoryType",
            "MorningModule",
            "PartialCaptionPayload",
            "PlaybackPolicy",
            "PresenceState",
            "PresenceStatePayload",
            "ResumeOfferPayload",
            "SafetyLevel",
            "SessionReadyPayload",
            "SessionStartPayload",
            "SourceState",
            "TaraTurnPayload",
            "TranscriptStatus",
            "TtsChunkMetaPayload",
            "TtsEndPayload",
            "TtsStartPayload",
            "UserTurnPayload",
            "VadState",
            "VadStatePayload",
        ]
    ):
        lines.append(f'    "{name}",')
    lines += [
        "]",
        "",
    ]
    (PY_OUT / "__init__.py").write_text("\n".join(lines), encoding="utf-8")


# ------------------------------------------------------------ call media
#
# Python only, deliberately. `apps/web` never speaks this protocol — it is the
# socket BETWEEN two of our services, behind the §34.6 one the browser sees —
# so a TypeScript mirror would be a set no consumer reads, which is how a
# declared contract goes stale without anyone noticing. Same reasoning the
# package already applies to `facts.py` and `cache_keys.py`: the mirror is
# deferred until a frontend consumer exists, not omitted by accident.


def gen_call_media(call_media: dict) -> None:
    lines = [
        f'"""{HEADER}',
        "",
        "SPEC §25.3 / §25.7 — the internal media socket between `sitara-realtime`",
        "and `sitara-api`. Declared here because BOTH sides name the set, which is",
        "this package's rule; see the source JSON for why it is not §34.6.",
        '"""',
        "",
        "from enum import StrEnum",
        "",
        "__all__ = [",
    ]
    exports = [
        *(e["enum_name"] for e in call_media["enums"].values()),
        *(e["const_name"] for e in call_media["enums"].values()),
        *call_media["constants"],
    ]
    for name in sorted(exports):
        lines.append(f'    "{name}",')
    lines += ["]", ""]
    for enum in call_media["enums"].values():
        lines += py_enum(enum)
        lines += [
            "",
            f"{enum['const_name']}: tuple[{enum['enum_name']}, ...] = (",
            *(f"    {enum['enum_name']}.{py_ident(m['id'])}," for m in enum["members"]),
            ")",
            "",
        ]
    for name, const in call_media["constants"].items():
        lines += ["", f"#: {const['$comment']}", f"{name} = {py_const(const['value'])}"]
    lines.append("")
    (PY_OUT / "call_media.py").write_text("\n".join(lines), encoding="utf-8")


# ------------------------------------------------------------ typescript

def gen_typescript(
    modules: dict,
    codes: dict,
    envelope: dict,
    ws: dict,
    confidence: dict,
    today: dict,
    presence: dict,
    memory_types: dict,
    chat: dict,
    voice: dict,
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
        "  ack: number | null;",
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
        "// SPEC §4.3 — Tara's twelve presence states.",
        "// ONE source, because the client and the server each had their own twelve",
        "// and five of them disagreed — by name and by position. See the JSON.",
        "// ---------------------------------------------------------------------------",
    ]
    lines += ts_enum(presence)
    lines += [
        "/** §4.3's own numbering. Documentation and a threshold operand — never the wire. */",
        "export const PRESENCE_ORDINAL: Record<PresenceState, number> = {",
    ]
    for member_id, ordinal in ordinals(presence).items():
        lines.append(f"  {member_id}: {ordinal},")
    lines += [
        "};",
        "",
        "// ---------------------------------------------------------------------------",
        "// SPEC §32.4 — the eleven memory types. Vault filters use exactly these.",
        "// ---------------------------------------------------------------------------",
    ]
    lines += ts_enum(memory_types)
    lines += [
        "// ---------------------------------------------------------------------------",
        "// SPEC §25.4 / §30.4 — one chat turn, as it crosses the wire.",
        "// ---------------------------------------------------------------------------",
    ]
    for enum in chat["enums"].values():
        lines += ts_enum(enum)
    safety = chat["enums"]["safety_level"]
    lines += [
        "/** §9's ladder as numbers, for the one comparison both sides make. */",
        f"export const SAFETY_LEVEL_ORDINAL: Record<{safety['enum_name']}, number> = {{",
    ]
    for member_id, ordinal in ordinals(safety).items():
        lines.append(f"  {member_id}: {ordinal},")
    lines += ["};", ""]
    for name, const in chat["constants"].items():
        lines += [f"/** {const['$comment']} */", f"export const {name} = {const['value']} as const;", ""]
    for name, shape in chat["shapes"].items():
        lines += ts_shape(name, shape)
    lines += [
        "// ---------------------------------------------------------------------------",
        "// SPEC §33.1 / §6.4 / §25.4 — the vocabulary of a voice note.",
        "// `playback_policy` is what makes §25.4's promise checkable: replay plays the",
        "// user's ORIGINAL recording, and `synthesised` — the one member under which",
        "// audio is a reconstruction — is never valid on a user message.",
        "// ---------------------------------------------------------------------------",
    ]
    for enum in voice["enums"].values():
        lines += ts_enum(enum)
    for name, const in voice["constants"].items():
        lines += [
            f"/** {const['$comment']} */",
            f"export const {name} = {const['value']} as const;",
            "",
        ]
    lines += [
        "// ---------------------------------------------------------------------------",
        "// SPEC §34.6 — control-event payloads: the text chat (S18), voice notes",
        "// (M9) and the live call (M10). All fifteen members are typed now; the",
        "// member SET is unchanged and stays closed at fifteen (§31.3).",
        "// ---------------------------------------------------------------------------",
    ]
    for name, shape in ws["payload_shapes"].items():
        lines += ts_shape(name, shape)
    lines += [
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
        lines += ts_shape(name, shape)
    (TS_OUT / "index.ts").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    modules = load("modules.json")
    codes = load("error-codes.json")
    envelope = load("error-envelope.json")
    ws = load("ws-events.json")
    confidence = load("confidence-states.json")
    today = load("today.json")
    presence = load("presence-states.json")
    memory_types = load("memory-types.json")
    chat = load("chat.json")
    voice = load("voice.json")
    call_media = load("call-media.json")

    assert len(modules["members"]) == 17, "SPEC §34.3: exactly 17 morning modules"
    assert len(confidence["members"]) == 5, "SPEC §5.4: exactly 5 confidence states"
    assert len(ws["members"]) == 15, "SPEC §34.6: closed set of 15 control events"
    assert len(presence["members"]) == 12, "SPEC §4.3: exactly 12 presence states"
    assert len(memory_types["members"]) == 11, "SPEC §32.4: exactly 11 memory types"
    # §4.3 and §32.4 both NUMBER their members, and the numbering is what a
    # reader checks this file against the spec with. A gap in it means one was
    # dropped in an edit and the list still looks complete.
    for source, spec in ((presence, "§4.3"), (memory_types, "§32.4")):
        assert [m["ordinal"] for m in source["members"]] == list(
            range(1, len(source["members"]) + 1)
        ), f"{spec} numbers its members 1..n with no gaps"
    for m in codes["members"]:
        assert any(m["code"].startswith(ns) for ns in codes["namespaces"]), (
            f"error code {m['code']} outside closed namespaces"
        )

    # §25.4 rests on one sentence — "replay plays the user's ORIGINAL recording,
    # never a TTS reconstruction" — and `playback_policy` is what makes it
    # checkable at runtime. If the member naming the reconstruction were ever
    # renamed or dropped, every guard that refuses it on a user message would
    # still compile and would simply stop refusing anything.
    policies = {m["id"] for m in voice["enums"]["playback_policy"]["members"]}
    assert "synthesised" in policies and "original_audio" in policies, (
        "SPEC §25.4/§33.1: playback_policy must distinguish the user's original "
        "recording from a TTS reconstruction — that distinction IS the promise"
    )

    gen_python(modules, codes, envelope, ws, today, presence, memory_types, chat, voice)
    gen_call_media(call_media)
    gen_typescript(
        modules, codes, envelope, ws, confidence, today, presence, memory_types, chat, voice
    )
    print(
        "generated: python/sitara_schemas/"
        "{__init__,modules,errors,ws_events,today,presence,memory_types,chat,voice,"
        "call_media}.py"
    )
    print("generated: typescript/src/index.ts")


if __name__ == "__main__":
    main()
