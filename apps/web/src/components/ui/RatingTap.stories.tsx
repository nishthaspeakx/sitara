import type { Meta, StoryObj } from "@storybook/nextjs";
import { useState } from "react";

import { RatingTap, type RatingChoice } from "./RatingTap";
import { StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Feedback/RatingTap",
  component: RatingTap,
  args: { onRate: () => {} },
  parameters: {
    docs: {
      description: {
        component:
          "§30.4 — the feedback fabric, everywhere guidance appears. 'This looks wrong' is the important one: it routes into structured triage and, when adjudication finds a served fact wrong, into a user-visible correction. Once answered it becomes an acknowledgement, not a scoreboard.",
      },
    },
  },
} satisfies Meta<typeof RatingTap>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Unanswered: Story = {};
export const Helpful: Story = { args: { value: "helpful" } };
export const NotRelevant: Story = { args: { value: "not_relevant" } };
export const LooksWrong: Story = { args: { value: "looks_wrong" } };

export const Interactive: Story = {
  render: function InteractiveDemo() {
    const [value, setValue] = useState<RatingChoice | null>(null);
    return <RatingTap value={value} onRate={setValue} />;
  },
};

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="unanswered" row>
        <RatingTap onRate={() => {}} />
      </StateGroup>
      <StateGroup name="acknowledgements — no counts, no streaks">
        <RatingTap value="helpful" onRate={() => {}} />
        <RatingTap value="not_relevant" onRate={() => {}} />
        <RatingTap value="looks_wrong" onRate={() => {}} />
      </StateGroup>
    </StatePanel>
  ),
};
