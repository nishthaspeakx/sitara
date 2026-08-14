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


def test_twelve_presence_states_everywhere() -> None:
    """§4.3's twelve, in one place at last.

    They were in two, and the two disagreed. `sitara_api` numbered §4.3 exactly
    while `apps/web`'s `TARA_STATES` had invented `warm_neutral`, `smile`,
    `full_smile`, `reading` and `safety`, and had dropped `calm_guidance` and
    `encouragement` outright. Five of twelve differed — and differed by
    POSITION, so the server's state 11 (safety-still, the one §29.5 puts in the
    chat header at L2+) was the client's `reading`.

    Nothing failed because nothing had ever consumed a served presence state.
    S18 is the first screen that does.
    """
    from sitara_schemas import PRESENCE_ORDINAL, PresenceState

    source = src("presence-states.json")
    ids = [m["id"] for m in source["members"]]
    assert len(ids) == 12
    assert sorted(p.value for p in PresenceState) == sorted(ids)
    assert ts_const_array("PRESENCE_STATES") == ids
    assert [PRESENCE_ORDINAL[PresenceState(i)] for i in ids] == list(range(1, 13))


def test_eleven_memory_types_everywhere() -> None:
    """§32.4: "Vault filters use exactly these 11 labels, localized".

    `packages/i18n` declared a different eleven for a milestone —
    `life_fact`, `concern`, `belief_practice`, `conversation_thread` and three
    more that §32.4 does not contain. Seven of eleven disagreed. The lint reads
    this file now (`dynamic-keys.json`'s `valuesFrom`), so a catalog can no
    longer carry a label the taxonomy has never heard of.
    """
    from sitara_schemas import MEMORY_TYPE_ORDER, MemoryType

    ids = [m["id"] for m in src("memory-types.json")["members"]]
    assert len(ids) == 11
    assert sorted(m.value for m in MemoryType) == sorted(ids)
    assert [m.value for m in MEMORY_TYPE_ORDER] == ids
    assert ts_const_array("MEMORY_TYPES") == ids


def test_voice_note_vocabulary_agrees_across_both_languages() -> None:
    """§33.1/§6.4's message fields, which the two languages already disagreed on.

    `sitara_api...store` wrote `transcript_status: "not_applicable"` and
    `playback_policy: "text_only"`; `apps/web`'s VoiceNoteBubble declared
    `"ready" | "pending" | "failed" | "none"`. Neither had crossed the wire, so
    nothing failed — the same invisibility that hid the confidence states, the
    presence states and the memory types until the first screen rendered one.
    """
    from sitara_schemas import PLAYBACK_POLICIES, TRANSCRIPT_STATUSES, VAD_STATES

    source = src("voice.json")
    for key, const_tuple, ts_name in (
        ("transcript_status", TRANSCRIPT_STATUSES, "TRANSCRIPT_STATUSES"),
        ("playback_policy", PLAYBACK_POLICIES, "PLAYBACK_POLICIES"),
        ("vad_state", VAD_STATES, "VAD_STATES"),
    ):
        ids = [m["id"] for m in source["enums"][key]["members"]]
        assert [m.value for m in const_tuple] == ids, key
        assert ts_const_array(ts_name) == ids, ts_name


def test_playback_policy_can_tell_a_recording_from_a_reconstruction() -> None:
    """§25.4: "replay plays the user's ORIGINAL recording, never a TTS
    reconstruction". The promise is only checkable if the wire can distinguish
    the two, so the distinction is asserted here rather than left to the
    stores and components that depend on it.
    """
    from sitara_schemas import PlaybackPolicy

    assert PlaybackPolicy.ORIGINAL_AUDIO != PlaybackPolicy.SYNTHESISED
    # §33.1's ephemeral mode and its expiry both land here, and neither is an
    # error state: the bubble shows the transcript with a "voice input" marker.
    assert PlaybackPolicy.TRANSCRIPT_ONLY in PlaybackPolicy


def test_chat_turn_agrees_across_both_languages() -> None:
    """§25.4's turn, over HTTP and over the socket, is ONE shape."""
    import sitara_schemas.chat as chat_mod

    source = src("chat.json")
    for spec in source["enums"].values():
        ids = [m["id"] for m in spec["members"]]
        enum = getattr(chat_mod, spec["enum_name"])
        assert sorted(m.value for m in enum) == sorted(ids), spec["enum_name"]
        assert ts_const_array(spec["const_name"]) == ids, spec["const_name"]

    for name, shape in source["shapes"].items():
        declared = [f["name"] for f in shape["fields"]]
        assert list(getattr(chat_mod, name).model_fields) == declared, f"{name} (python)"
        m = re.search(rf"export interface {name} \{{(.*?)\n\}}", TS_INDEX, re.S)
        assert m, f"{name} missing from typescript/src/index.ts"
        assert re.findall(r"^\s+(\w+):", m.group(1), re.M) == declared, f"{name} (ts)"


def test_chat_turn_cannot_carry_a_fact_id() -> None:
    """§30.4, held to the standard `today.json` is already held to.

    The chat router used to serve whole `FactSnapshot`s "so the Trust Sheet
    renders from what was served" — and a snapshot carries its `fact_id`. Now
    that §30.4's three layers are rendered server-side there is nothing the
    snapshots were for, and no field here one could travel in.
    """
    for name, shape in src("chat.json")["shapes"].items():
        for field in shape["fields"]:
            assert "fact_id" not in field["name"], f"{name}.{field['name']}"


def test_control_event_carries_an_ack() -> None:
    """§34.6: "server acks control events by seq".

    There is no `ack` MEMBER to carry that — the set is closed at fifteen — so
    it rides on the event the server sends in reply. Without a field for it the
    sentence in the spec is unimplementable, which is how it stayed
    unimplemented through M0.
    """
    from sitara_schemas import ControlEvent

    declared = [f["name"] for f in src("ws-events.json")["control_event_shape"]["fields"]]
    assert "ack" in declared
    assert list(ControlEvent.model_fields) == declared
    m = re.search(r"export interface ControlEvent \{(.*?)\n\}", TS_INDEX, re.S)
    assert m and re.findall(r"^\s+(\w+):", m.group(1), re.M) == declared


def test_a_payload_is_typed_by_the_milestone_that_emits_it() -> None:
    """§34.6 defers payload typing to "M9". The rule this encodes is narrower
    and is the one that has actually held: a member gets a payload shape in the
    milestone that starts EMITTING it, never before — because typing an event
    nothing produces is a guess with a schema around it.

    S18 typed the text-chat subset a milestone early on that rule. M9 typed
    `vad.state` and `tts.*` when voice notes began emitting them. **M10 types
    the last two** — `barge_in` (§25.3's server-side VAD ducking) and
    `entitlement.warning` (§7.3's minute pool, §32.9's 5- and 2-minute
    notices) — because M10's live call is the milestone that sends them.

    So the "not yet" half of this test is now empty, and the assertion that
    remains is the one that outlives the milestone: every member of the closed
    fifteen has a shape, and none of them may be dropped. The direction that
    used to fail (a shape arriving before its emitter) can no longer occur
    without also adding a sixteenth member, which is §31.3 change control.
    """
    import sitara_schemas.ws_events as ws_mod

    source = src("ws-events.json")
    for name, shape in source["payload_shapes"].items():
        declared = [f["name"] for f in shape["fields"]]
        assert list(getattr(ws_mod, name).model_fields) == declared, name

    # Every shape a milestone has landed must stay landed. S18's, M9's, M10's —
    # listed by name rather than counted, so deleting one fails here instead of
    # quietly reducing a total nobody reads.
    for member in (
        "SessionStartPayload",
        "SessionReadyPayload",
        "UserTurnPayload",
        "PartialCaptionPayload",
        "TaraTurnPayload",
        "PresenceStatePayload",
        "HandoffToTextPayload",
        "ResumeOfferPayload",
        "VadStatePayload",
        "TtsStartPayload",
        "TtsChunkMetaPayload",
        "TtsEndPayload",
        "BargeInPayload",
        "EntitlementWarningPayload",
    ):
        assert member in source["payload_shapes"], f"{member} is emitted and must stay typed"


def test_a_cut_utterance_ends_in_barge_in_and_never_in_tts_end() -> None:
    """§25.3's barge-in, held in the shapes rather than in a convention.

    `tts.end` carries `duration_ms` — the total, for the bubble's scrubber. An
    utterance the user interrupted has no total that was ever true, so a
    synthesis stream ends in exactly one of two members: `tts.end` when it
    finished, `barge_in` when it did not. A client can therefore rely on
    "audio stopped" always having a reason attached, which is what stops
    §25.3's interruption from rendering as a glitch.

    The check is structural: `BargeInPayload` must name the chunk it stopped
    after, because a client buffering ahead of playback cannot otherwise tell
    what the server had already put on the wire — and audio that keeps playing
    after the interruption is precisely what barge-in exists to prevent.
    """
    from sitara_schemas import BargeInPayload, TtsEndPayload

    assert "duration_ms" in TtsEndPayload.model_fields
    assert "duration_ms" not in BargeInPayload.model_fields
    assert "cancelled_after_chunk_seq" in BargeInPayload.model_fields
    assert "reason" in BargeInPayload.model_fields


def test_the_minute_warnings_are_declared_once_for_both_sides() -> None:
    """§32.9's two thresholds, in the package both sides read.

    The server decides when to send `entitlement.warning`; the client decides
    when §25.3's plan chip stops saying "unlimited" and starts counting. Those
    are the same two numbers or they are two implementations of one promise —
    the drift this package exists to prevent, and the reason the constant is
    here rather than in either service.
    """
    from sitara_schemas import ENTITLEMENT_WARNING_MINUTES

    assert ENTITLEMENT_WARNING_MINUTES == (5, 2)
    assert isinstance(ENTITLEMENT_WARNING_MINUTES, tuple), (
        "a mutable shared constant is a shared constant anyone can change at runtime"
    )


def test_a_partial_caption_can_only_ever_be_the_users_own_speech() -> None:
    """§34.6's `$never_emitted_for_tara`, made unrepresentable.

    §9 runs grounding, language-quality and safety-post AFTER generation, so a
    partial caption of Tara's words would be pre-validation text racing three
    validators to the screen. Through M8 the guarantee was that no code wrote
    the frame. M9 writes it — for the user's own speech — so the guarantee has
    to live in the type instead: `role` is the constant "user", not a ChatRole.
    """
    import pydantic
    import pytest
    from sitara_schemas import PartialCaptionPayload

    assert PartialCaptionPayload(role="user", text="aaj", client_message_id="c1").role == "user"
    with pytest.raises(pydantic.ValidationError):
        PartialCaptionPayload(role="tara", text="the Moon is in Rohini", client_message_id="c1")

    ts = re.search(r"export interface PartialCaptionPayload \{(.*?)\n\}", TS_INDEX, re.S)
    assert ts and 'role: "user";' in ts.group(1), (
        "the TypeScript side must pin `role` too — a client that can construct a "
        "Tara partial is a client that can render one"
    )


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
