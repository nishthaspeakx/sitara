"""§25.3's live call, on the API side (§25.7's "call-session service").

The call is split across two services and the split is not arbitrary:

    browser  ──§34.6──▶  sitara-realtime  ──media socket──▶  sitara-api  ──▶  vendors
                          protocol, VAD,                      §9 pipeline,
                          metering clock,                     STT/TTS adapters,
                          degrade ladder                      entitlements, storage

§25.7 puts the session state machine in `sitara-realtime`, and `sitara-realtime`
holds no database, no model client and no vendor credentials — an invariant this
module does not weaken. So realtime owns everything about the CALL and this
module owns everything about the TURN, which is the same division `/v1/chat/ws/*`
already draws for the text socket.

`media.py` is the one description of the socket between them, read by both.
"""
