import type { Meta, StoryObj } from "@storybook/nextjs";

import { CallControls } from "./CallControls";
import { StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Sitara/CallControls",
  component: CallControls,
  args: {
    muted: false,
    onToggleMute: () => {},
    speakerOn: true,
    onToggleSpeaker: () => {},
    onEnd: () => {},
  },
  parameters: {
    docs: {
      description: {
        component:
          "§25.3 / S19 — end-call is EXPLICIT: the largest target, always labelled, never behind an overflow. Call audio is never stored, and the privacy line says so here rather than in a policy page (§33.1).",
      },
    },
  },
} satisfies Meta<typeof CallControls>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const Muted: Story = { args: { muted: true } };
export const WithCaptions: Story = { args: { captionsOn: true, onToggleCaptions: () => {} } };
/** The minute meter appears only from 20% remaining (§S19) — no earlier nagging. */
export const MinutesRunningLow: Story = {
  args: { minutesLeft: 4, minutesTotal: 30, onOpenPlan: () => {} },
};

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="default · muted · speaker off · captions">
        <CallControls
          muted={false}
          onToggleMute={() => {}}
          speakerOn
          onToggleSpeaker={() => {}}
          onEnd={() => {}}
        />
        <CallControls
          muted
          onToggleMute={() => {}}
          speakerOn={false}
          onToggleSpeaker={() => {}}
          captionsOn
          onToggleCaptions={() => {}}
          onEnd={() => {}}
        />
      </StateGroup>
      <StateGroup name="minutes running low — the meter appears at ≤20%">
        <CallControls
          muted={false}
          onToggleMute={() => {}}
          speakerOn
          onToggleSpeaker={() => {}}
          onEnd={() => {}}
          minutesLeft={4}
          minutesTotal={30}
          onOpenPlan={() => {}}
        />
      </StateGroup>
    </StatePanel>
  ),
};
