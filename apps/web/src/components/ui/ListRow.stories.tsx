import type { Meta, StoryObj } from "@storybook/nextjs";
import { Bell } from "lucide-react";

import { ListRow } from "./ListRow";
import { Toggle } from "./Toggle";
import { ICON_STROKE } from "./_util";
import { SAMPLE, StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Structure/ListRow",
  component: ListRow,
  args: { labelKey: "ui.notif.class.daily" },
} satisfies Meta<typeof ListRow>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Static: Story = {};
export const Navigational: Story = { args: { onClick: () => {} } };
export const WithLeading: Story = {
  args: { leading: <Bell strokeWidth={ICON_STROKE} />, onClick: () => {} },
};
export const WithUserData: Story = { args: { labelKey: undefined, label: SAMPLE.name } };

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="static · navigational · with a trailing control">
        <ListRow labelKey="ui.notif.class.daily" detailKey="ui.notif.always_on" />
        <ListRow
          labelKey="ui.tabs.journal"
          leading={<Bell strokeWidth={ICON_STROKE} />}
          onClick={() => {}}
        />
        <ListRow
          labelKey="ui.notif.class.marketing"
          trailing={
            <Toggle labelKey="ui.toggle.on" checked={false} onChange={() => {}} />
          }
        />
      </StateGroup>
      <StateGroup name="user data as the label · disabled">
        <ListRow label={SAMPLE.name} detail={SAMPLE.city} onClick={() => {}} />
        <ListRow labelKey="ui.tabs.you" onClick={() => {}} disabled />
      </StateGroup>
    </StatePanel>
  ),
};
