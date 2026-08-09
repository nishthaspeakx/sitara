import type { Meta, StoryObj } from "@storybook/nextjs";

import { NotificationPrefRow } from "./NotificationPrefRow";
import { StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Feedback/NotificationPrefRow",
  component: NotificationPrefRow,
  args: {
    classKey: "ui.notif.class.daily",
    channels: { push: "on", whatsapp: "off", email: "on" },
    onToggle: () => {},
  },
  parameters: {
    docs: {
      description: {
        component:
          "§23.5 matrix row. Transactional cannot be switched off and the row says why in words. A channel the user has not granted shows its state honestly and offers the §30.1 recovery path instead of silently failing to deliver.",
      },
    },
  },
} satisfies Meta<typeof NotificationPrefRow>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Daily: Story = {};
export const Transactional: Story = {
  args: {
    classKey: "ui.notif.class.transactional",
    channels: { push: "on", whatsapp: "on", email: "on" },
    locked: true,
  },
};
/** Push denied — §30.1's recovery path, not a silent failure. */
export const ChannelUnavailable: Story = {
  args: {
    channels: { push: "unavailable", whatsapp: "on", email: "on" },
    onFixChannel: () => {},
  },
};

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="the four §23.4 classes">
        <NotificationPrefRow
          classKey="ui.notif.class.transactional"
          descriptionKey="ui.notif.always_on"
          channels={{ push: "on", whatsapp: "on", email: "on" }}
          locked
        />
        <NotificationPrefRow
          classKey="ui.notif.class.daily"
          channels={{ push: "on", whatsapp: "off", email: "on" }}
          onToggle={() => {}}
        />
        <NotificationPrefRow
          classKey="ui.notif.class.conversational"
          channels={{ push: "unavailable", whatsapp: "on", email: "off" }}
          onToggle={() => {}}
          onFixChannel={() => {}}
        />
        <NotificationPrefRow
          classKey="ui.notif.class.marketing"
          channels={{ push: "off", whatsapp: "off", email: "off" }}
          onToggle={() => {}}
        />
      </StateGroup>
    </StatePanel>
  ),
};
