import type { Meta, StoryObj } from "@storybook/nextjs";

import { VoiceNoteBubble } from "./VoiceNoteBubble";
import { SAMPLE, StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Sitara/VoiceNoteBubble",
  component: VoiceNoteBubble,
  args: { mode: "idle", duration: "0:12", speed: 1 },
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

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="record · play · speed">
        <VoiceNoteBubble mode="recording" duration="0:04" onStopRecording={() => {}} />
        <VoiceNoteBubble mode="idle" duration="0:12" speed={1} onCycleSpeed={() => {}} />
        <VoiceNoteBubble mode="playing" duration="0:12" speed={1.5} onCycleSpeed={() => {}} />
        <VoiceNoteBubble mode="playing" duration="0:12" speed={2} onCycleSpeed={() => {}} />
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
        <VoiceNoteBubble mode="idle" duration="0:12" expiresOn={SAMPLE.date} />
      </StateGroup>
    </StatePanel>
  ),
};
