import type { Meta, StoryObj } from "@storybook/nextjs";

import { VoiceBar, VOICE_STATES } from "./VoiceBar";
import { StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Sitara/VoiceBar",
  component: VoiceBar,
  args: { state: "idle" },
} satisfies Meta<typeof VoiceBar>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Idle: Story = {};
export const Listening: Story = { args: { state: "listening" } };
export const Processing: Story = { args: { state: "processing" } };
export const Speaking: Story = { args: { state: "speaking" } };
export const Error: Story = { args: { state: "error" } };
/** §30.1 — denied is not a dead end: the affordance stays, with the ⓘ recovery path. */
export const MicDenied: Story = { args: { state: "idle", micDenied: true } };

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="idle · listening · processing · speaking · error">
        {VOICE_STATES.map((state) => (
          <VoiceBar key={state} state={state} />
        ))}
      </StateGroup>
      <StateGroup name="microphone denied (§30.1) — text always works">
        <VoiceBar state="idle" micDenied />
      </StateGroup>
    </StatePanel>
  ),
};
