import type { Meta, StoryObj } from "@storybook/nextjs";

import { Skeleton } from "./Skeleton";
import { StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Feedback/Skeleton",
  component: Skeleton,
  args: { variant: "brief" },
  parameters: {
    docs: {
      description: {
        component:
          "§24.6 — skeletons MIRROR the final layout; no spinners on content surfaces. Tara's breathing doubles as conversational loading, which is why there is no Tara skeleton. The shimmer stops under reduced motion and the block stays informative.",
      },
    },
  },
} satisfies Meta<typeof Skeleton>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Brief: Story = { args: { variant: "brief" } };
export const Chat: Story = { args: { variant: "chat", count: 4 } };
export const List: Story = { args: { variant: "list", count: 5 } };

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="brief">
        <Skeleton variant="brief" count={2} />
      </StateGroup>
      <StateGroup name="chat">
        <Skeleton variant="chat" count={4} />
      </StateGroup>
      <StateGroup name="list">
        <Skeleton variant="list" count={4} />
      </StateGroup>
    </StatePanel>
  ),
};
