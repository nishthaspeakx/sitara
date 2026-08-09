import type { Meta, StoryObj } from "@storybook/nextjs";

import { Toast } from "./Toast";
import { StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Feedback/Toast",
  component: Toast,
  args: { open: true, messageKey: "ui.memory.accepted", onDismiss: () => {} },
  parameters: {
    layout: "fullscreen",
    docs: {
      description: {
        component:
          "§24.3 — bottom, auto-dismiss, NEVER stacked more than one. The single-slot rule is enforced in the component, not left to callers: a second Toast that opens while the slot is held renders nothing. Auto-dismiss pauses on hover and focus, and never applies to a toast with an action.",
      },
    },
  },
} satisfies Meta<typeof Toast>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Neutral: Story = { args: { autoDismissMs: 1_000_000 } };
export const Success: Story = { args: { tone: "success", autoDismissMs: 1_000_000 } };
/** With an action there is no auto-dismiss — an unreachable action is a dark pattern. */
export const WithAction: Story = {
  args: { actionKey: "ui.memory.forget", onAction: () => {} },
};

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="one toast holds the slot; the second renders nothing">
        <div className="relative min-h-[12rem]">
          <Toast
            open
            messageKey="ui.memory.accepted"
            actionKey="ui.memory.forget"
            onAction={() => {}}
            onDismiss={() => {}}
          />
          <Toast open messageKey="ui.receipt.paid" tone="success" onDismiss={() => {}} />
        </div>
      </StateGroup>
    </StatePanel>
  ),
};
