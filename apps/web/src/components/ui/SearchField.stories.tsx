import type { Meta, StoryObj } from "@storybook/nextjs";
import { useState } from "react";

import { SearchField } from "./SearchField";
import { StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Foundation/SearchField",
  component: SearchField,
  args: { value: "", onChange: () => {} },
} satisfies Meta<typeof SearchField>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Empty: Story = {};
export const WithQuery: Story = { args: { value: "wedding" } };

export const Interactive: Story = {
  render: function InteractiveDemo() {
    const [value, setValue] = useState("");
    return <SearchField value={value} onChange={setValue} />;
  },
};

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="empty">
        <SearchField value="" onChange={() => {}} />
      </StateGroup>
      <StateGroup name="with query — the clear control appears">
        <SearchField value="wedding" onChange={() => {}} />
      </StateGroup>
      <StateGroup name="disabled">
        <SearchField value="" onChange={() => {}} disabled />
      </StateGroup>
    </StatePanel>
  ),
};
