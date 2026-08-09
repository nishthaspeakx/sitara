import type { Meta, StoryObj } from "@storybook/nextjs";

import { OfflineBanner } from "./OfflineBanner";
import { StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Feedback/OfflineBanner",
  component: OfflineBanner,
  args: {},
  parameters: {
    docs: {
      description: {
        component:
          "§24.6 / §6.2 — offline is never a blank screen: the banner sits above cached content and the composer stays usable with messages queued. Informational, not an alarm, so it does not borrow the danger colour.",
      },
    },
  },
} satisfies Meta<typeof OfflineBanner>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Plain: Story = {};
export const WithCacheTime: Story = { args: { cachedAt: "07:04", onRetry: () => {} } };
export const WithQueue: Story = { args: { queued: 3, onRetry: () => {} } };

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="plain · cached · queued messages waiting">
        <OfflineBanner />
        <OfflineBanner cachedAt="07:04" onRetry={() => {}} />
        <OfflineBanner cachedAt="07:04" queued={3} onRetry={() => {}} />
        <OfflineBanner cachedAt="07:04" queued={1} onRetry={() => {}} />
      </StateGroup>
    </StatePanel>
  ),
};
