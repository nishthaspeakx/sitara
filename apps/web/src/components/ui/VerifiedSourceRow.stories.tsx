import type { Meta, StoryObj } from "@storybook/nextjs";

import { VerifiedSourceRow } from "./VerifiedSourceRow";
import { StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Sitara/VerifiedSourceRow",
  component: VerifiedSourceRow,
  args: { state: "default" },
} satisfies Meta<typeof VerifiedSourceRow>;

export default meta;
type Story = StoryObj<typeof meta>;

export const TwoSources: Story = { args: { state: "default" } };
export const SingleSource: Story = { args: { state: "single" } };
/** Deliberately calm: almanacs disagreeing is not a warning to the user. */
export const Disputed: Story = { args: { state: "disputed" } };

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="default · single · disputed (§34.7)">
        <VerifiedSourceRow state="default" />
        <VerifiedSourceRow state="single" />
        <VerifiedSourceRow state="disputed" />
      </StateGroup>
    </StatePanel>
  ),
};
