import type { Meta, StoryObj } from "@storybook/nextjs";
import { useState } from "react";

import { TabBar, TABS, type TabId } from "./TabBar";
import { StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Structure/TabBar",
  component: TabBar,
  args: { active: "today", onSelect: () => {} },
  parameters: {
    docs: {
      description: {
        component:
          "§24.1 (FINAL): four tabs — Today · Ask Tara · Journal · You. Night reflection is Today's evening state, NOT a fifth tab. Labels hide at 320px and the icons carry the tabs (§29.3).", // token-lint-disable-line — spec citation in prose
      },
    },
  },
} satisfies Meta<typeof TabBar>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Today: Story = {};
export const WithBadges: Story = { args: { badges: { ask: 2, journal: 1 } } };

export const Interactive: Story = {
  render: function InteractiveDemo() {
    const [active, setActive] = useState<TabId>("today");
    return <TabBar active={active} onSelect={setActive} />;
  },
};

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="each of the four tabs active">
        {TABS.map((tab) => (
          <TabBar key={tab} active={tab} onSelect={() => {}} />
        ))}
      </StateGroup>
      <StateGroup name="with badges">
        <TabBar active="today" onSelect={() => {}} badges={{ ask: 2, journal: 1 }} />
      </StateGroup>
    </StatePanel>
  ),
};
