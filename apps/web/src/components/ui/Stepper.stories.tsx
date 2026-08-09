import type { Meta, StoryObj } from "@storybook/nextjs";

import { Stepper, type Step } from "./Stepper";
import { StateGroup, StatePanel } from "./_story-utils";

const STEPS: Step[] = [
  { labelKey: "ui.paywall.plans" },
  { labelKey: "ui.paywall.gift" },
  { labelKey: "ui.receipt.paid" },
];

const meta = {
  title: "Structure/Stepper",
  component: Stepper,
  args: { steps: STEPS, current: 2 },
} satisfies Meta<typeof Stepper>;

export default meta;
type Story = StoryObj<typeof meta>;

export const First: Story = { args: { current: 1 } };
export const Middle: Story = { args: { current: 2, onStepBack: () => {} } };
export const Last: Story = { args: { current: 3, onStepBack: () => {} } };

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="each position — completed steps stay reachable">
        <Stepper steps={STEPS} current={1} />
        <Stepper steps={STEPS} current={2} onStepBack={() => {}} />
        <Stepper steps={STEPS} current={3} onStepBack={() => {}} />
      </StateGroup>
    </StatePanel>
  ),
};
