import type { Meta, StoryObj } from "@storybook/nextjs";

import { Chip } from "./Chip";
import { StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Foundation/Chip",
  component: Chip,
  args: { children: "Work" },
} satisfies Meta<typeof Chip>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Choice: Story = { args: { variant: "choice" } };
export const Filter: Story = { args: { variant: "filter", count: 12 } };
export const MemoryConsent: Story = { args: { variant: "memory-consent" } };

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="choice" row>
        <Chip>Work</Chip>
        <Chip selected>Work</Chip>
        <Chip disabled>Work</Chip>
      </StateGroup>
      <StateGroup name="filter" row>
        <Chip variant="filter" count={12}>
          Reflections
        </Chip>
        <Chip variant="filter" selected count={3}>
          Reflections
        </Chip>
      </StateGroup>
      <StateGroup name="memory-consent" row>
        <Chip variant="memory-consent">Remember this</Chip>
        <Chip variant="memory-consent" selected>
          Remember this
        </Chip>
      </StateGroup>
    </StatePanel>
  ),
};
