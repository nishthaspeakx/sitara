import type { Meta, StoryObj } from "@storybook/nextjs";
import { useState } from "react";

import { ReflectionPrompt } from "./ReflectionPrompt";
import { StateGroup, StatePanel } from "./_story-utils";

const PROMPT = "What went better than you expected today?";

const meta = {
  title: "Sitara/ReflectionPrompt",
  component: ReflectionPrompt,
  args: { prompt: PROMPT, value: "", onChange: () => {} },
} satisfies Meta<typeof ReflectionPrompt>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Empty: Story = { args: { index: 1, total: 3, onSkip: () => {} } };
export const Answered: Story = {
  args: { value: "The conversation I was dreading was kind.", index: 2, total: 3 },
};

export const Interactive: Story = {
  render: function InteractiveDemo() {
    const [value, setValue] = useState("");
    return (
      <ReflectionPrompt
        prompt={PROMPT}
        value={value}
        onChange={setValue}
        index={1}
        total={3}
        onSkip={() => {}}
      />
    );
  },
};

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="empty — save is disabled, and skipping is a first-class answer">
        <ReflectionPrompt
          prompt={PROMPT}
          value=""
          onChange={() => {}}
          index={1}
          total={3}
          onSkip={() => {}}
        />
      </StateGroup>
      <StateGroup name="answered">
        <ReflectionPrompt
          prompt={PROMPT}
          value="The conversation I was dreading was kind."
          onChange={() => {}}
          index={2}
          total={3}
          onSkip={() => {}}
        />
      </StateGroup>
    </StatePanel>
  ),
};
