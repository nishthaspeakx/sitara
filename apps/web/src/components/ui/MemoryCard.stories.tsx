import type { Meta, StoryObj } from "@storybook/nextjs";

import { MemoryCard, MEMORY_TYPES } from "./MemoryCard";
import { SAMPLE, StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Sitara/MemoryCard",
  component: MemoryCard,
  args: { type: "life_fact", content: SAMPLE.memory, consentedOn: SAMPLE.date },
} satisfies Meta<typeof MemoryCard>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const WithSourceLink: Story = { args: { onOpenSource: () => {} } };

/** All 11 §32.4 memory types, each with its consent stamp. */
export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="the 11 memory types (§32.4)">
        {MEMORY_TYPES.map((type) => (
          <MemoryCard
            key={type}
            type={type}
            content={SAMPLE.memory}
            consentedOn={SAMPLE.date}
            onOpenSource={() => {}}
          />
        ))}
      </StateGroup>
    </StatePanel>
  ),
};
