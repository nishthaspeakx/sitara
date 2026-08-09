import type { Meta, StoryObj } from "@storybook/nextjs";

import { ConfidenceChip } from "./ConfidenceChip";
import { CONFIDENCE_STATES } from "./_util";
import { StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Sitara/ConfidenceChip",
  component: ConfidenceChip,
  args: { state: "verified" },
  parameters: {
    docs: {
      description: {
        component:
          "§34.7 — all five treatments, and NEITHER Approximate nor Cannot-calculate uses a caution or danger colour. An honest limit is not a warning (§9, no fear-selling).",
      },
    },
  },
} satisfies Meta<typeof ConfidenceChip>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Verified: Story = { args: { state: "verified" } };
export const VerifiedLimited: Story = { args: { state: "verified_limited_birth_data" } };
export const Approximate: Story = { args: { state: "approximate" } };
export const TraditionGeneral: Story = { args: { state: "tradition_based_general" } };
export const CannotCalculate: Story = { args: { state: "cannot_calculate" } };

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="the five treatments (§34.7)" row>
        {CONFIDENCE_STATES.map((state) => (
          <ConfidenceChip key={state} state={state} />
        ))}
      </StateGroup>
      <StateGroup name="with description">
        {CONFIDENCE_STATES.map((state) => (
          <ConfidenceChip key={state} state={state} withDescription />
        ))}
      </StateGroup>
    </StatePanel>
  ),
};
