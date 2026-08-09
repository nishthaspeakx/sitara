import type { Meta, StoryObj } from "@storybook/nextjs";
import { useState } from "react";

import { SegmentedControl, type Segment } from "./SegmentedControl";
import { StateGroup, StatePanel } from "./_story-utils";

const SEGMENTS: Segment[] = [
  { value: "today", labelKey: "ui.tabs.today" },
  { value: "journal", labelKey: "ui.tabs.journal" },
  { value: "you", labelKey: "ui.tabs.you" },
];

const meta = {
  title: "Foundation/SegmentedControl",
  component: SegmentedControl,
  args: {
    labelKey: "ui.tabs.label",
    segments: SEGMENTS,
    value: "today",
    onChange: () => {},
  },
} satisfies Meta<typeof SegmentedControl>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const LastSelected: Story = { args: { value: "you" } };
export const Disabled: Story = { args: { disabled: true } };

export const Interactive: Story = {
  render: function InteractiveDemo() {
    const [value, setValue] = useState("today");
    return (
      <SegmentedControl
        labelKey="ui.tabs.label"
        segments={SEGMENTS}
        value={value}
        onChange={setValue}
      />
    );
  },
};

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="each segment active" row>
        {SEGMENTS.map((s) => (
          <SegmentedControl
            key={s.value}
            labelKey="ui.tabs.label"
            segments={SEGMENTS}
            value={s.value}
            onChange={() => {}}
          />
        ))}
      </StateGroup>
      <StateGroup name="two segments · disabled" row>
        <SegmentedControl
          labelKey="ui.tabs.label"
          segments={SEGMENTS.slice(0, 2)}
          value="today"
          onChange={() => {}}
        />
        <SegmentedControl
          labelKey="ui.tabs.label"
          segments={SEGMENTS}
          value="today"
          onChange={() => {}}
          disabled
        />
      </StateGroup>
    </StatePanel>
  ),
};
