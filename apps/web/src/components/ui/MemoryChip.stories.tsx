import type { Meta, StoryObj } from "@storybook/nextjs";

import { MemoryChip } from "./MemoryChip";
import { SAMPLE, StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Sitara/MemoryChip",
  component: MemoryChip,
  args: { state: "offer", summary: SAMPLE.memory },
  parameters: {
    docs: {
      description: {
        component:
          "§32.4 — a memory is OFFERED, never taken. Accept and decline carry equal weight; remembering is not the default (§29.2).",
      },
    },
  },
} satisfies Meta<typeof MemoryChip>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Offer: Story = {};
export const Accepted: Story = { args: { state: "accepted", onForget: () => {} } };
export const Declined: Story = { args: { state: "declined" } };

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="offer · accepted · declined">
        <MemoryChip state="offer" summary={SAMPLE.memory} onAccept={() => {}} onDecline={() => {}} />
        <MemoryChip state="accepted" summary={SAMPLE.memory} onForget={() => {}} />
        <MemoryChip state="declined" summary={SAMPLE.memory} />
      </StateGroup>
    </StatePanel>
  ),
};
