import type { Meta, StoryObj } from "@storybook/nextjs";
import { useState } from "react";

import { Select, type SelectOption } from "./Select";
import { StateGroup, StatePanel } from "./_story-utils";

const OPTIONS: SelectOption[] = [
  { value: "en", labelKey: "ui.tabs.today" },
  { value: "hi", labelKey: "ui.tabs.ask" },
  { value: "hi-Latn", labelKey: "ui.tabs.journal" },
];

const meta = {
  title: "Foundation/Select",
  component: Select,
  args: { labelKey: "ui.select.choose", options: OPTIONS, value: null, onChange: () => {} },
} satisfies Meta<typeof Select>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Placeholder: Story = {};
export const Selected: Story = { args: { value: "hi" } };
/** The picker is a Sheet, not a native menu — long Indic labels get full width. */
export const SheetOpen: Story = { args: { value: "hi", defaultOpen: true } };

export const Interactive: Story = {
  render: function InteractiveDemo() {
    const [value, setValue] = useState<string | null>(null);
    return (
      <Select labelKey="ui.select.choose" options={OPTIONS} value={value} onChange={setValue} />
    );
  },
};

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="placeholder">
        <Select labelKey="ui.select.choose" options={OPTIONS} value={null} onChange={() => {}} />
      </StateGroup>
      <StateGroup name="selected">
        <Select labelKey="ui.select.choose" options={OPTIONS} value="hi" onChange={() => {}} />
      </StateGroup>
      <StateGroup name="disabled">
        <Select
          labelKey="ui.select.choose"
          options={OPTIONS}
          value={null}
          onChange={() => {}}
          disabled
        />
      </StateGroup>
    </StatePanel>
  ),
};
