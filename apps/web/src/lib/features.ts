/**
 * Feature flags that gate BUILT code, not missing code.
 *
 * A flag here means the thing exists, has a test, and is deliberately not
 * rendering. Anything unbuilt belongs in a milestone, not in this file — a
 * flag over a hole is how "flagged off" starts meaning "not written".
 */

/**
 * §25.4's voice notes — dark until M9.
 *
 * `VoiceNoteBubble` and `VoiceBar` are in the §24.3 library with their full
 * state sets, `ChatBubble` has its audio variant wired, and none of it renders
 * in the composer or the thread. What is NOT built is the half that makes any
 * of it honest: §33.1's encrypted 30-day storage of the original recording, and
 * §25.4's rule that replay plays **the user's own audio and never a TTS
 * reconstruction**. Shipping a microphone button before that storage exists
 * would mean either losing the recording or quietly replacing it with
 * synthesis — and §25.4 names the second one as the thing not to do.
 *
 * M9 flips this after the audio path lands. `tests/ask-voice-dark.spec.ts`
 * asserts that nothing renders while it is false.
 */
export const VOICE_NOTES_ENABLED = false;
