"use client";

/**
 * CC-014's demo bridge — Hindi listening, in the browser, prototype only.
 *
 * Chrome's Web Speech API transcribes `hi-IN` locally-ish and the finalised
 * text goes up §34.6's socket as a `captions.final`, which is the frame Ink's
 * own finals already take. Nothing downstream changes: the server cannot tell
 * this turn from a typed one, and every §9 validator runs on it unmodified.
 *
 * ── This is not the Indic recogniser, and it never becomes one ─────────────
 *
 * The server decides whether the bridge may run at all: the grant carries
 * `browser_stt_lang`, non-null only when `SITARA_PROTOTYPE` is active on a dev
 * machine and only for the locales CC-010 leaves without a recogniser. This
 * module has **no way to turn itself on** — there is no flag here, no env read
 * and no locale check of its own. If the field is null there is no bridge.
 *
 * `routing.CAPABILITIES` is untouched, so `calls_available_in("hi")` is still
 * false and §33.5's gate still reads BLOCKED. See
 * `services/api/src/sitara_api/voice/providers/browser_bridge.py`.
 *
 * ── Audio reaches Google ───────────────────────────────────────────────────
 *
 * `SpeechRecognition` in Chrome is a network service: the microphone stream
 * goes to Google's servers. That is a third-party processor with no DPA
 * receiving a user's voice, which is why this is confined to a local demo with
 * synthetic personas, and why the screen says so the whole time it is running.
 *
 * ── Never a silent degrade ─────────────────────────────────────────────────
 *
 * If the API is absent — any non-Chrome browser — `start()` returns null and
 * the caller must refuse the call exactly as it does today. An English
 * recogniser fed Hindi audio produces fluent nonsense that reaches §9 as the
 * user's question, and that failure is the entire reason CC-010 exists. A
 * bridge that fell back to `en-US` would be that failure with extra steps.
 */

/** Chrome exposes it prefixed; nothing else exposes it at all. */
type RecognitionCtor = new () => SpeechRecognitionLike;

interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
}

interface SpeechRecognitionEventLike {
  resultIndex: number;
  results: ArrayLike<
    ArrayLike<{ transcript: string }> & { isFinal: boolean }
  >;
}

function recognitionCtor(): RecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: RecognitionCtor;
    webkitSpeechRecognition?: RecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

/**
 * Whether this browser could run the bridge at all.
 *
 * Asked by the screen so a non-Chrome browser gets today's honest refusal
 * rather than a call that opens and then hears nothing.
 */
export function browserSttSupported(): boolean {
  return recognitionCtor() !== null;
}

export interface BrowserSttHandlers {
  /** A finalised utterance. Goes up as `captions.final`. */
  onFinal: (text: string) => void;
  /** An interim guess, for the on-screen caption only. Never sent up. */
  onPartial?: (text: string) => void;
  /** The recogniser gave up — the caller shows the refusal. */
  onUnavailable: (reason: string) => void;
}

export interface BrowserStt {
  stop: () => void;
}

/**
 * Start local recognition in `lang`, or return null if this browser cannot.
 *
 * `lang` comes from the SERVER (`grant.browser_stt_lang`) and is never chosen
 * here — that is what keeps the locale ruling in one place instead of two.
 */
export function startBrowserStt(
  lang: string,
  handlers: BrowserSttHandlers,
): BrowserStt | null {
  const Ctor = recognitionCtor();
  if (!Ctor) return null;

  const recognition = new Ctor();
  recognition.lang = lang;
  // Continuous: a call is a conversation, not a single utterance.
  recognition.continuous = true;
  // Interims drive the on-screen caption only. §34.6's `captions.partial` is
  // SERVER→client and its `role` is the constant "user"; an interim is
  // replaceable by definition, so sending one up would put text into §9 that
  // the speaker had not finished saying.
  recognition.interimResults = true;

  let stopped = false;

  recognition.onresult = (event) => {
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const result = event.results[i];
      if (!result) continue;
      const text = (result[0]?.transcript ?? "").trim();
      if (!text) continue;
      if (result.isFinal) {
        handlers.onFinal(text);
      } else {
        handlers.onPartial?.(text);
      }
    }
  };

  recognition.onerror = (event) => {
    // `no-speech` and `aborted` are ordinary in a conversation with pauses;
    // anything else means the recogniser is not going to work, and the caller
    // falls back to the refusal rather than leaving a call listening to
    // nothing.
    if (event.error === "no-speech" || event.error === "aborted") return;
    stopped = true;
    handlers.onUnavailable(event.error);
  };

  recognition.onend = () => {
    // Chrome ends the session on its own after a pause. Restart unless we
    // stopped deliberately — otherwise a call goes quietly deaf mid-sentence
    // and looks like Tara ignoring the user.
    if (stopped) return;
    try {
      recognition.start();
    } catch {
      stopped = true;
      handlers.onUnavailable("restart-failed");
    }
  };

  try {
    recognition.start();
  } catch (error) {
    return null;
  }

  return {
    stop: () => {
      stopped = true;
      recognition.abort();
    },
  };
}
