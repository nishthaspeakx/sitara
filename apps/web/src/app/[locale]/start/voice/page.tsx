"use client";

/**
 * S12 — voice preview (§29.1 `/start/voice`, §24.4, §30.1).
 *
 * "Tara says the name; fix-pronunciation affordance; voice on/off."
 *
 * The microphone is NOT asked for here. §30.1 is explicit: the mic explainer
 * fires "at first voice action only (mic tap or call button)", and this screen
 * has the user LISTENING, not speaking. Asking now would be a permission
 * request before its value has been shown, which is the pattern §30.1 exists
 * to prevent.
 *
 * The TTS render itself belongs to the voice module (§3.3), which is not built.
 * Rather than fake a playback that produces silence, the player renders its
 * `unavailable` state — which is a designed state, and true. §5.3's discipline
 * applied to a feature rather than a fact: say what is so.
 */

import { useTranslations } from "next-intl";
import { useState } from "react";

import {
  AudioPlayer,
  Button,
  Card,
  ErrorState,
  SectionHeader,
  TaraPresence,
  Toggle,
} from "@/components/ui";
import { patchState, STEPS, useOnboarding } from "@/lib/onboarding";

import { useStepCommit } from "../_step";

export default function VoicePage() {
  const t = useTranslations();
  const { displayName, voiceEnabled, set } = useOnboarding();
  const { commit, busy, error, clearError } = useStepCommit(STEPS.VOICE);
  const [playing, setPlaying] = useState(false);

  return (
    <main className="mx-auto flex max-w-md flex-col gap-6 px-6 pb-12">
      <div className="flex justify-center">
        <TaraPresence size="lg" state="speaking_soft" still showAiLabel />
      </div>

      <SectionHeader titleKey="start.voice.title" subtitleKey="start.voice.subtitle" />

      <Card as="section" className="flex flex-col gap-4">
        {displayName ? (
          <p className="font-serif text-h2 text-ink-primary" data-testid="voice-name">
            {displayName}
          </p>
        ) : null}

        <AudioPlayer
          playing={playing}
          onTogglePlay={() => setPlaying((p) => !p)}
          progress={0}
          elapsed="0:00"
          duration="0:00"
          // The §3.3 voice module has not shipped. A player that pretended to
          // play would be a promise the product cannot keep on the screen whose
          // subject is Tara's voice.
          unavailable
        />

        <Button variant="tertiary" data-testid="fix-pronunciation">
          {t("start.voice.fix_pronunciation")}
        </Button>
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
