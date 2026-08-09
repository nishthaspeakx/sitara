import type { Meta, StoryObj } from "@storybook/nextjs";

import { Divider } from "./Divider";
import { StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Structure/Divider",
  component: Divider,
} satisfies Meta<typeof Divider>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Decorative by default, so it never adds noise to the screen-reader tree. */
export const Plain: Story = {};
export const Labelled: Story = { args: { labelKey: "auth.or" } };
export const Vertical: Story = { args: { orientation: "vertical" } };

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="plain (decorative) · labelled (a real separator)">
        <Divider />
        <Divider labelKey="auth.or" />
      </StateGroup>
      <StateGroup name="vertical">
        <div className="flex h-8 items-center gap-3">
          <span className="text-caption text-ink-muted">Today</span>
          <Divider orientation="vertical" />
          <span className="text-caption text-ink-muted">Tomorrow</span>
        </div>
      </StateGroup>
    </StatePanel>
  ),
};
