/**
 * Feature flags that gate BUILT code, not missing code.
 *
 * A flag here means the thing exists, has a test, and is deliberately not
 * rendering. Anything unbuilt belongs in a milestone, not in this file — a
 * flag over a hole is how "flagged off" starts meaning "not written".
 */

/**
 * §25.4's voice notes — LIVE since M9.
 *
 * The flag stays as a kill switch rather than being deleted: voice touches a
 * microphone, a vendor and thirty days of stored audio, and an operator needs
 * one lever that turns all three off without a deploy.
 *
 * What it used to gate, and what changed. Through M7–M8 this was false because
 * §33.1's encrypted storage of the ORIGINAL recording did not exist, and
 * without it §25.4's "replay plays the user's own audio, never a TTS
 * reconstruction" could not be honoured — a mic button before that storage is a
 * promise the app cannot keep. M9 built it: `voice_assets` under its own CSFLE
 * key class, a 30-day expiry job that hard-deletes and tombstones, per-note
 * delete, and §33.1's ephemeral mode that never writes at all.
 *
 * One correction worth recording here, because this file made the claim. The
 * old comment cited `tests/ask-voice-dark.spec.ts` as asserting that nothing
 * rendered while the flag was false. **That file never existed**, and
 * `Composer.tsx` carried `{VOICE_NOTES_ENABLED ? null : null}` — a no-op that
 * reads as a gate. The flag was documented as mechanically enforced and was
 * not. `tests/ask-voice.spec.ts` is the real test, and it drives a recording
 * against the real socket stub rather than asserting an absence.
 */
export const VOICE_NOTES_ENABLED = true;
