import type { Meta, StoryObj } from "@storybook/nextjs";
import { useState } from "react";

import { Button } from "./Button";
import { Sheet } from "./Sheet";
import { StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Structure/Sheet",
  component: Sheet,
  args: {
    open: true,
    onClose: () => {},
    titleKey: "ui.trust.title",
    children: <p className="text-body text-ink-primary">Sheet content.</p>,
  },
  parameters: {
    layout: "fullscreen",
    docs: {
      description: {
        component:
          "The app's default overlay. §29.2: the close control is always visible, Escape always works, focus is trapped while open — a sheet is never a dead end.",
      },
    },
  },
} satisfies Meta<typeof Sheet>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Open: Story = {
  args: { children: <p className="text-body text-ink-primary">Sheet content.</p> },
};
export const WithDescription: Story = {
  args: {
    descriptionKey: "ui.confidence.verified_desc",
    children: <p className="text-body text-ink-primary">Sheet content.</p>,
  },
};
export const WithFooter: Story = {
  args: {
    children: <p className="text-body text-ink-primary">Sheet content.</p>,
    footer: <Button fullWidth>Continue</Button>,
  },
};

export const Interactive: Story = {
  render: function InteractiveDemo() {
    const [open, setOpen] = useState(false);
    return (
      <div className="p-4">
        <Button onClick={() => setOpen(true)}>Open the sheet</Button>
        <Sheet open={open} onClose={() => setOpen(false)} titleKey="ui.trust.title">
          <p className="text-body text-ink-primary">Escape closes this. So does the ✕.</p>
        </Sheet>
      </div>
    );
  },
};

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="open, with description and a footer action">
        <div className="relative min-h-[28rem]">
          <Sheet
            open
            onClose={() => {}}
            titleKey="ui.trust.title"
            descriptionKey="ui.confidence.verified_desc"
            footer={<Button fullWidth>Continue</Button>}
          >
            <p className="max-w-reading text-body text-ink-primary">
              The close control is always visible — there is no state in which this sheet traps you.
            </p>
          </Sheet>
        </div>
      </StateGroup>
    </StatePanel>
  ),
};
