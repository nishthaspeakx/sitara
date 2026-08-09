import type { Meta, StoryObj } from "@storybook/nextjs";

import { Modal } from "./Modal";
import { StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Structure/Modal",
  component: Modal,
  args: {
    open: true,
    onClose: () => {},
    titleKey: "ui.memory.forget",
    bodyKey: "ui.memory.offer",
    confirmKey: "ui.memory.forget",
    onConfirm: () => {},
  },
  parameters: {
    layout: "fullscreen",
    docs: {
      description: {
        component:
          "Marked 'rare' in §24.3 — reserved for a decision that cannot be deferred and cannot be undone. Focus lands on cancel, never on the irreversible action, and the destructive confirm is not the gold button.",
      },
    },
  },
} satisfies Meta<typeof Modal>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Confirm: Story = {};
export const Destructive: Story = { args: { destructive: true } };
export const Busy: Story = { args: { busy: true } };

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="destructive — confirm is the plain control, focus starts on cancel">
        <div className="relative min-h-[22rem]">
          <Modal
            open
            onClose={() => {}}
            titleKey="ui.memory.forget"
            bodyKey="ui.memory.offer"
            confirmKey="ui.memory.forget"
            onConfirm={() => {}}
            destructive
          />
        </div>
      </StateGroup>
    </StatePanel>
  ),
};
