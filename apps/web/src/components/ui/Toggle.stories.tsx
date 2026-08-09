import type { Meta, StoryObj } from "@storybook/nextjs";
import { useState } from "react";

import { Toggle } from "./Toggle";
import { StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Foundation/Toggle",
  component: Toggle,
  args: { labelKey: "ui.notif.class.daily", checked: false, onChange: () => {} },
} satisfies Meta<typeof Toggle>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Off: Story = {};
export const On: Story = { args: { checked: true } };
export const WithDescription: Story = {
  args: { checked: true, descriptionKey: "ui.notif.always_on" },
};

export const Interactive: Story = {
  render: function InteractiveDemo() {
    const [on, setOn] = useState(false);
    return <Toggle labelKey="ui.notif.class.daily" checked={on} onChange={setOn} />;
  },
};

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="off · on">
        <Toggle labelKey="ui.notif.class.daily" checked={false} onChange={() => {}} />
        <Toggle labelKey="ui.notif.class.daily" checked onChange={() => {}} />
      </StateGroup>
      <StateGroup name="with description">
        <Toggle
          labelKey="ui.notif.class.transactional"
          descriptionKey="ui.notif.always_on"
          checked
          onChange={() => {}}
        />
      </StateGroup>
      <StateGroup name="disabled">
        <Toggle labelKey="ui.notif.class.marketing" checked={false} onChange={() => {}} disabled />
      </StateGroup>
    </StatePanel>
  ),
};
