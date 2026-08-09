import type { Meta, StoryObj } from "@storybook/nextjs";
import { useState } from "react";

import { Slider } from "./Slider";
import { StateGroup, StatePanel } from "./_story-utils";

/** Brief time in 15-minute steps; the value is announced as a clock time. */
const formatTime = (value: number) => {
  const hours = String(Math.floor(value / 4)).padStart(2, "0");
  const minutes = String((value % 4) * 15).padStart(2, "0");
  return `${hours}:${minutes}`;
};

const meta = {
  title: "Foundation/Slider",
  component: Slider,
  args: {
    labelKey: "ui.notif.class.daily",
    min: 16,
    max: 44,
    value: 28,
    onChange: () => {},
    format: formatTime,
  },
} satisfies Meta<typeof Slider>;

export default meta;
type Story = StoryObj<typeof meta>;

export const BriefTime: Story = {};
export const Disabled: Story = { args: { disabled: true } };

export const Interactive: Story = {
  render: function InteractiveDemo() {
    const [value, setValue] = useState(28);
    return (
      <Slider
        labelKey="ui.notif.class.daily"
        min={16}
        max={44}
        value={value}
        onChange={setValue}
        format={formatTime}
      />
    );
  },
};

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="07:00 — the default brief time">
        <Slider
          labelKey="ui.notif.class.daily"
          min={16}
          max={44}
          value={28}
          onChange={() => {}}
          format={formatTime}
        />
      </StateGroup>
      <StateGroup name="at the ends of the range">
        <Slider
          labelKey="ui.notif.class.daily"
          min={16}
          max={44}
          value={16}
          onChange={() => {}}
          format={formatTime}
        />
        <Slider
          labelKey="ui.notif.class.daily"
          min={16}
          max={44}
          value={44}
          onChange={() => {}}
          format={formatTime}
        />
      </StateGroup>
      <StateGroup name="disabled">
        <Slider
          labelKey="ui.notif.class.daily"
          min={16}
          max={44}
          value={28}
          onChange={() => {}}
          format={formatTime}
          disabled
        />
      </StateGroup>
    </StatePanel>
  ),
};
