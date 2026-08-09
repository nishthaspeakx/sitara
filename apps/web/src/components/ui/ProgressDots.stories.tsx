import type { Meta, StoryObj } from "@storybook/nextjs";

import { ONBOARDING_STEPS, ProgressDots } from "./ProgressDots";
import { StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Structure/ProgressDots",
  component: ProgressDots,
  args: { current: 6 },
  parameters: {
    docs: {
      description: {
        component:
          "§24.4 — every onboarding screen carries these, and back always works. The dots are decorative; the position is announced in words, so it is never colour-only or shape-only information.",
      },
    },
  },
} satisfies Meta<typeof ProgressDots>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Start: Story = { args: { current: 1 } };
export const Midway: Story = { args: { current: 6 } };
export const Last: Story = { args: { current: ONBOARDING_STEPS } };
export const ShortFlow: Story = { args: { current: 2, total: 4 } };

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name={`the 13-step onboarding flow (§24.4)`}>
        <ProgressDots current={1} />
        <ProgressDots current={6} />
        <ProgressDots current={ONBOARDING_STEPS} />
      </StateGroup>
      <StateGroup name="a shorter flow">
        <ProgressDots current={2} total={4} />
      </StateGroup>
    </StatePanel>
  ),
};
