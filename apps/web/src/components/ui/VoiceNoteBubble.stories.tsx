import type { Meta, StoryObj } from "@storybook/nextjs";

import { VoiceNoteBubble } from "./VoiceNoteBubble";
import { SAMPLE, StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Sitara/VoiceNoteBubble",
  component: VoiceNoteBubble,
  args: { mode: "idle", duration: "0:12", speed: 1, src: "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAgD4AAAB9AAACABAAZGF0YQAAAAA=" },
  parameters: {
    docs: {
      description: {
        component:
          "§33.1 — the original audio is stored encrypted for 30 days by default and the bubble SAYS when it expires. Call audio is never stored, so there is no call variant here.",
      },
    },
  },
} satisfies Meta<typeof VoiceNoteBubble>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Recording: Story = { args: { mode: "recording", onStopRecording: () => {} } };
export const Idle: Story = { args: { mode: "idle", onCycleSpeed: () => {} } };
export const Playing: Story = { args: { mode: "playing", speed: 1.5 } };
export const WithTranscript: Story = {
  args: { transcriptStatus: "ready", transcript: SAMPLE.transcript },
};
export const TranscriptPending: Story = { args: { transcriptStatus: "pending" } };
export const TranscriptFailed: Story = { args: { transcriptStatus: "failed" } };
/**
 * §33.1's honest drop: the recording expired, was deleted per-note, or was
 * never stored (ephemeral voice-input mode). No `src`, so NO play control at
 * all — a greyed-out one would still say "there is a recording here", which is
 * exactly what stopped being true.
 */
export const NoRecording: Story = {
  args: {
    src: undefined,
    transcriptStatus: "ready",
    transcript: SAMPLE.transcript,
    markerKey: "ui.audio.voice_input",
  },
};

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="record · play · speed">
        <VoiceNoteBubble mode="recording" duration="0:04" onStopRecording={() => {}} />
        <VoiceNoteBubble mode="idle" duration="0:12" speed={1} src={"data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAgD4AAAB9AAACABAAZGF0YQAAAAA="} onCycleSpeed={() => {}} />
        <VoiceNoteBubble mode="playing" duration="0:12" speed={1.5} src={"data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAgD4AAAB9AAACABAAZGF0YQAAAAA="} onCycleSpeed={() => {}} />
        <VoiceNoteBubble mode="playing" duration="0:12" speed={2} src={"data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAgD4AAAB9AAACABAAZGF0YQAAAAA="} onCycleSpeed={() => {}} />
      </StateGroup>
      <StateGroup name="transcript — ready · pending · failed (§6.4 transcript_status)">
        <VoiceNoteBubble
          mode="idle"
          duration="0:12"
          transcriptStatus="ready"
          transcript={SAMPLE.transcript}
        />
        <VoiceNoteBubble mode="idle" duration="0:12" transcriptStatus="pending" />
        <VoiceNoteBubble mode="idle" duration="0:12" transcriptStatus="failed" />
      </StateGroup>
      <StateGroup name="the 30-day retention is stated, not implied (§33.1)">
        <VoiceNoteBubble mode="idle" duration="0:12" src={"data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAgD4AAAB9AAACABAAZGF0YQAAAAA="} expiresOn={SAMPLE.date} />
      </StateGroup>
      <StateGroup name="no recording — expired, deleted, or never stored (§33.1)">
        {/* The play control is ABSENT, not disabled. §33.1 has the bubble
            "honestly drop playback of expired/deleted audio and show the
            transcript with a 'voice input' marker" — a greyed button would
            still assert that a recording exists. */}
        <VoiceNoteBubble
          mode="idle"
          duration="0:12"
          transcriptStatus="ready"
          transcript={SAMPLE.transcript}
          markerKey="ui.audio.voice_input"
        />
      </StateGroup>
    </StatePanel>
  ),
};
