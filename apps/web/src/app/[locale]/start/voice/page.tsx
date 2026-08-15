"use client";

/**
 * S12 — voice preview (§29.1 `/start/voice`, §24.4, §30.1).
 *
 * §0.11 item 11: "hear Tara say the user's name (pronunciation confirm/fix —
 * stores override), choose voice on/off default." All three now work.
 *
 * The microphone is NOT asked for here. §30.1 is explicit: the mic explainer
 * fires "at first voice action only (mic tap or call button)", and this screen
 * has the user LISTENING, not speaking. Asking now would be a permission
 * request before its value has been shown, which is the pattern §30.1 exists
 * to prevent.
 *
 * **This screen sends no text to the synthesiser, and cannot.** `POST
 * /v1/voice/preview` takes no body — the sentence is a catalog key resolved
 * server-side in the account's locale, and the only thing that varies is the
 * user's own name. That is `speak_holding_phrase`'s rule (§25.3) applied to the
 * second surface that needs arbitrary-looking words spoken; see
 * `services/api/src/sitara_api/voice/preview.py` for why it is a signature
 * rather than a convention.
 *
 * When the synthesiser is unavailable the player renders its `unavailable`
 * state, which is a DESIGNED state and true — §5.3's discipline applied to a
 * feature rather than a fact. What it must never do is render a play button
 * that produces silence.
 */

import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import {
  AudioPlayer,
  Button,
  Card,
  ErrorState,
  Input,
  SectionHeader,
  TaraPresence,
  Toggle,
} from "@/components/ui";
import { patchState, STEPS, useOnboarding } from "@/lib/onboarding";
import {
  fetchVoicePreview,
  revokeVoicePreview,
  saveNamePronunciation,
} from "@/lib/voice-preview";

import { useStepCommit } from "../_step";

type PreviewPhase = "idle" | "loading" | "ready" | "unavailable";

export default function VoicePage() {
  const t = useTranslations();
  const { displayName, voiceEnabled, set } = useOnboarding();
  const { commit, busy, error, clearError } = useStepCommit(STEPS.VOICE);

  const [phase, setPhase] = useState<PreviewPhase>("idle");
  const [playing, setPlaying] = useState(false);
  const [fixing, setFixing] = useState(false);
  const [spokenAs, setSpokenAs] = useState("");

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const urlRef = useRef<string | null>(null);

  // A blob URL pins its bytes until revoked, and this screen is replayable as
  // many times as someone likes — so every fetch revokes the last one, and
  // unmount revokes the current one.
  useEffect(() => {
    return () => {
      audioRef.current?.pause();
      revokeVoicePreview(urlRef.current);
    };
  }, []);

  async function play() {
    if (phase === "loading") return;
    setPhase("loading");
    const result = await fetchVoicePreview();
    if (!result.ok) {
      // §30.1: her voice being unavailable is a designed state on this screen.
      // The step still completes — voice is not a gate on onboarding.
      setPhase("unavailable");
      return;
    }
    revokeVoicePreview(urlRef.current);
    urlRef.current = result.url;

    const audio = audioRef.current ?? new Audio();
    audioRef.current = audio;
    audio.src = result.url;
    audio.onended = () => setPlaying(false);
    setPhase("ready");
    setPlaying(true);
    try {
      await audio.play();
    } catch {
      // Autoplay policies reject playback that is not user-gestured. This one
      // always is, but a rejection must not leave the button stuck mid-play.
      setPlaying(false);
    }
  }

  function togglePlay() {
    const audio = audioRef.current;
    if (playing && audio) {
      audio.pause();
      setPlaying(false);
      return;
    }
    if (phase === "ready" && audio) {
      setPlaying(true);
      void audio.play().catch(() => setPlaying(false));
      return;
    }
    void play();
  }

  async function saveFix(next: string | null) {
    await saveNamePronunciation(next);
    setFixing(false);
    // Hearing the correction IS the confirmation — §0.11's "confirm/fix" loop
    // closes by playing it back, not by showing a tick.
    void play();
  }

  return (
    <main className="mx-auto flex max-w-md flex-col gap-6 px-6 pb-12">
      <div className="flex justify-center">
        <TaraPresence
          size="lg"
          state={playing ? "speaking_soft" : "listening"}
          still={!playing}
          showAiLabel
        />
      </div>

      <SectionHeader titleKey="start.voice.title" subtitleKey="start.voice.subtitle" />

      <Card as="section" className="flex flex-col gap-4">
        {displayName ? (
          <p className="font-serif text-h2 text-ink-primary" data-testid="voice-name">
            {displayName}
          </p>
        ) : null}

        {phase === "idle" || phase === "loading" ? (
          <Button
            variant="secondary"
            loading={phase === "loading"}
            data-testid="voice-play"
            onClick={() => void play()}
          >
            {t("start.voice.play")}
          </Button>
        ) : (
          <AudioPlayer
            playing={playing}
            onTogglePlay={togglePlay}
            progress={0}
            elapsed="0:00"
            duration="0:00"
            unavailable={phase === "unavailable"}
          />
        )}

        {fixing ? (
          <div className="flex flex-col gap-3" data-testid="voice-fix">
            <Input
              labelKey="start.voice.fix_title"
              helperKey="start.voice.fix_help"
              placeholder={t("start.voice.fix_placeholder")}
              value={spokenAs}
              onChange={(event) => setSpokenAs(event.target.value)}
              data-testid="voice-fix-input"
            />
            <div className="flex flex-wrap gap-2">
              <Button
                data-testid="voice-fix-save"
                disabled={!spokenAs.trim()}
                onClick={() => void saveFix(spokenAs.trim())}
              >
                {t("start.voice.fix_save")}
              </Button>
              {/* Clearing is its own control, not an empty save: "say it as
                  written" is a decision, and a user who has to erase a field to
                  express it cannot tell whether it took. */}
              <Button
                variant="tertiary"
                data-testid="voice-fix-clear"
                onClick={() => {
                  setSpokenAs("");
                  void saveFix(null);
                }}
              >
                {t("start.voice.fix_clear")}
              </Button>
              <Button
                variant="tertiary"
                data-testid="voice-fix-cancel"
                onClick={() => setFixing(false)}
              >
                {t("start.voice.fix_cancel")}
              </Button>
            </div>
          </div>
        ) : (
          <Button
            variant="tertiary"
            data-testid="fix-pronunciation"
            onClick={() => setFixing(true)}
          >
            {t("start.voice.fix_pronunciation")}
          </Button>
        )}
      </Card>

      <Card as="section">
        <Toggle
          labelKey="start.voice.voice_on_label"
          descriptionKey="start.voice.voice_on_help"
          checked={voiceEnabled}
          onChange={(next) => set({ voiceEnabled: next })}
        />
      </Card>

      <Button
        fullWidth
        loading={busy}
        data-testid="voice-continue"
        onClick={() =>
          void commit(() =>
            patchState({ voice_enabled: voiceEnabled, completed_step: STEPS.VOICE }),
          )
        }
      >
        {t("start.continue")}
      </Button>

      {error ? <ErrorState error={error} onRetry={clearError} /> : null}
    </main>
  );
}
