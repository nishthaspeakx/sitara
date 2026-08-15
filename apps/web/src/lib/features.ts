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

/**
 * §25.3's live calls — BUILT, and off (M9-P10b).
 *
 * This is the clearest case the file's own rule has had. Everything behind the
 * flag exists and is tested: the §34.6 call socket, server-side VAD and
 * barge-in, the streaming adapters, §7.3's minute pool, §32.9's warnings and
 * the whole §25.3 degrade ladder. The flag is not covering a hole.
 *
 * It is off because **§33.5 says so**. Live calls are a conditional release
 * gate — they ship "ONLY if" six measures pass, and today two of them are
 * BLOCKED (CC-010 leaves `hi`/`hi-Latn` with no streaming recogniser, so there
 * is no Hindi call in which to verify safety interception or rate naturalness)
 * and two are UNMEASURED. §33.5's own instruction for that state is the one
 * this flag implements: "launch proceeds with text + voice notes + Tara audio
 * replies, and calls roll out behind a flag when the gate passes."
 *
 * Run `uv run python -m sitara_api.voice.call_gate` to see the table. Turning
 * this on is a decision made against that output, not against this comment —
 * and the SERVER has the authoritative switch (`Settings.calls_enabled`), so
 * flipping this alone changes what the app OFFERS and not what it permits.
 */
export const CALLS_ENABLED = false;

/**
 * §25.3's calls, as the prototype demo may reach them (CC-014).
 *
 * `CALLS_ENABLED` above is the SHIPPED answer and stays false — §33.5 is
 * unmoved and `voice.call_gate` still does not pass. This is the separate
 * question of whether a local demo may open one, and it mirrors
 * `prototype.calls_enabled` on the server.
 *
 * **The server is the authority and this is a mirror, which is a cost worth
 * naming.** Every refusal is made at `POST /v1/call/session` — §33.5's flag,
 * CC-010's locale ruling and §7.3's pool are all evaluated there, and a client
 * that believed otherwise would simply be told no. This flag exists only so an
 * ENTRY POINT can decide whether to render before the user taps it, which is a
 * question no grant can answer in advance. If the two disagree, the grant wins
 * and the screen renders the refusal it already knows how to draw.
 *
 * In prototype mode `hi`/`hi-Latn` calls are reachable through CC-014's
 * browser-speech bridge, which labels itself on the call screen for the whole
 * call. So the entry points do NOT render a locale-disabled state during a
 * demo — there is nothing to disable.
 */
export const PROTOTYPE_CALLS = process.env.NEXT_PUBLIC_PROTOTYPE_CALLS === "1";

/** Whether a call entry point should render at all, for this locale. */
export function callEntryState(locale: string): "enabled" | "unsupported_locale" | "hidden" {
  if (PROTOTYPE_CALLS) return "enabled"; // CC-014's bridge covers all three.
  if (!CALLS_ENABLED) return "hidden";   // §33.5 — nothing to offer anyone.
  // Calls are live but this locale has no recogniser (CC-010). The control
  // renders DISABLED with its reason rather than vanishing: unlike the case
  // above, calling is a thing this product does — just not in this language
  // yet — and that is worth saying.
  return locale === "en" ? "enabled" : "unsupported_locale";
}
