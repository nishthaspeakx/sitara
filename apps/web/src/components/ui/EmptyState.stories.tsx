import type { Meta, StoryObj } from "@storybook/nextjs";

import { EmptyState, EMPTY_STATES } from "./EmptyState";
import { StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Feedback/EmptyState",
  component: EmptyState,
  args: { id: "memories", onAction: () => {} },
  parameters: {
    docs: {
      description: {
        component:
          "§24.6 fixes the count at NINE designed empty states: illustration + one line + one action, no dead ends. §29.5 keeps Tara off empty and failed screens — she is never the face of nothing-here.",
      },
    },
  },
} satisfies Meta<typeof EmptyState>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Memories: Story = { args: { id: "memories" } };
export const Journal: Story = { args: { id: "journal" } };
export const SearchResults: Story = { args: { id: "search_results" } };

/** All nine. A tenth cannot appear without a design-system review (§24.3). */
export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="the nine designed empty states (§24.6)">
        {EMPTY_STATES.map((id) => (
          <EmptyState key={id} id={id} onAction={() => {}} />
        ))}
      </StateGroup>
    </StatePanel>
  ),
};
