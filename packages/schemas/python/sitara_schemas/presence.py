"""GENERATED FILE — do not edit. Source: packages/schemas/src/*.json (run scripts/generate.py).

SPEC §4.3 — Tara's twelve presence states.

`sitara_api.chat_orchestration` and `apps/web`'s component library both
import from here. They each held their own twelve until M8-P10, and the
two disagreed on five of them by name AND by position — see the source
JSON's comment. The ID is the wire format; ORDINAL is §4.3's numbering.
"""

from enum import StrEnum


class PresenceState(StrEnum):
    """SPEC §4.3 — Tara's twelve presence states. CLOSED SET. Added in M8-P10 after the two languages turned out to hold DIFFERENT twelves: `sitara_api.chat_orchestration.types.PresenceState` numbered §4.3 exactly (1 welcome … 11 safety-still, 12 profile portrait) while `apps/web`'s `TARA_STATES` had invented `warm_neutral`/`smile`/`full_smile`/`reading`/`safety` and dropped `calm_guidance` and `encouragement` entirely. Five of the twelve disagreed, and they disagreed by POSITION as well as by name — index 11 was `safety_still` on the server and `reading` in the client. Nothing failed because no screen had ever consumed a served presence state; S18's chat header is the first, and §29.5 puts state 11 in exactly that header. The same story as the confidence states one milestone earlier, which is why this file exists rather than a third hand-written copy."""

    WELCOME = "welcome"
    LISTENING = "listening"
    SPEAKING_SOFT = "speaking_soft"
    THOUGHTFUL = "thoughtful"
    CALM_GUIDANCE = "calm_guidance"
    CONCERN_KIND = "concern_kind"
    ENCOURAGEMENT = "encouragement"
    CELEBRATION = "celebration"
    NIGHT = "night"
    FESTIVAL = "festival"
    SAFETY_STILL = "safety_still"
    PROFILE_PORTRAIT = "profile_portrait"


#: §4.3's own numbering. Kept so a trace can record the number the spec
#: uses and a reader can check this file against the spec line. NOT the
#: wire format: a positional contract is what drifted in the first place.
PRESENCE_ORDINAL: dict[PresenceState, int] = {
    PresenceState.WELCOME: 1,
    PresenceState.LISTENING: 2,
    PresenceState.SPEAKING_SOFT: 3,
    PresenceState.THOUGHTFUL: 4,
    PresenceState.CALM_GUIDANCE: 5,
    PresenceState.CONCERN_KIND: 6,
    PresenceState.ENCOURAGEMENT: 7,
    PresenceState.CELEBRATION: 8,
    PresenceState.NIGHT: 9,
    PresenceState.FESTIVAL: 10,
    PresenceState.SAFETY_STILL: 11,
    PresenceState.PROFILE_PORTRAIT: 12,
}

#: §4.3's ● marks — the states that have a cinemagraph loop. The delivered
#: kit is stills only (cinemagraphs are deferred post-beta, recorded in
#: apps/web's TARA_MOTION_STATUS); this is what §4.3 SPECIFIES, not what
#: has shipped, and the two are checked against each other there.
PRESENCE_CINEMAGRAPH: frozenset[PresenceState] = frozenset({
    PresenceState.WELCOME,
    PresenceState.LISTENING,
    PresenceState.SPEAKING_SOFT,
    PresenceState.CELEBRATION,
    PresenceState.NIGHT,
})
