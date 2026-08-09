import type { Meta, StoryObj } from "@storybook/nextjs";

import { Button } from "./Button";
import { SectionHeader } from "./SectionHeader";
import { StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Structure/SectionHeader",
  component: SectionHeader,
  args: { titleKey: "ui.tabs.journal" },
} satisfies Meta<typeof SectionHeader>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Level2: Story = {};
export const Level3: Story = { args: { level: 3 } };
export const WithSubtitle: Story = { args: { subtitleKey: "ui.empty.journal" } };
export const WithAction: Story = {
  args: { action: <Button variant="tertiary">See all</Button> },
};

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="h2 · h3 · with subtitle · with an action">
        <SectionHeader titleKey="ui.tabs.journal" />
        <SectionHeader titleKey="ui.tabs.journal" level={3} />
        <SectionHeader titleKey="ui.tabs.journal" subtitleKey="ui.empty.journal" />
        <SectionHeader
          titleKey="ui.tabs.journal"
          action={<Button variant="tertiary">See all</Button>}
        />
      </StateGroup>
    </StatePanel>
  ),
};
