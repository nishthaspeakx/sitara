import type { Meta, StoryObj } from "@storybook/nextjs";
import { Mic, Search, X } from "lucide-react";

import { IconButton } from "./IconButton";
import { ICON_STROKE } from "./_util";
import { StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Foundation/IconButton",
  component: IconButton,
  args: { labelKey: "ui.close", icon: <X strokeWidth={ICON_STROKE} /> },
} satisfies Meta<typeof IconButton>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Plain: Story = { args: { variant: "plain" } };
export const Filled: Story = { args: { variant: "filled" } };
export const Outline: Story = { args: { variant: "outline" } };

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      {(["plain", "filled", "outline"] as const).map((variant) => (
        <StateGroup key={variant} name={variant} row>
          <IconButton variant={variant} labelKey="ui.close" icon={<X strokeWidth={ICON_STROKE} />} />
          <IconButton
            variant={variant}
            labelKey="ui.search.label"
            icon={<Search strokeWidth={ICON_STROKE} />}
          />
          <IconButton
            variant={variant}
            labelKey="ui.call.mute"
            pressed
            icon={<Mic strokeWidth={ICON_STROKE} />}
          />
          <IconButton
            variant={variant}
            labelKey="ui.close"
            disabled
            icon={<X strokeWidth={ICON_STROKE} />}
          />
        </StateGroup>
      ))}
    </StatePanel>
  ),
};
