import type { Meta, StoryObj } from "@storybook/nextjs";

import { StoryRing } from "./StoryRing";
import { StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Sitara/StoryRing",
  component: StoryRing,
  args: { enabled: true, state: "unviewed", size: "sm" },
  parameters: {
    docs: {
      description: {
        component:
          "§30.6 — Stories are a P1 flag and the ring is HIDDEN in P0. `enabled` defaults to false, so a P0 build renders the bare portrait even if a screen forgets the flag.",
      },
    },
  },
} satisfies Meta<typeof StoryRing>;

export default meta;
type Story = StoryObj<typeof meta>;

/** The shipped P0 state: no ring, whatever the story state says. */
export const P0Hidden: Story = { args: { enabled: false, state: "unviewed" } };
export const Unviewed: Story = { args: { state: "unviewed" } };
export const Viewed: Story = { args: { state: "viewed" } };
export const None: Story = { args: { state: "none" } };

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="P0 — the flag is off, so there is no ring" row>
        <StoryRing enabled={false} state="unviewed" />
        <StoryRing enabled={false} state="viewed" />
      </StateGroup>
      <StateGroup name="P1 — unviewed · viewed · none" row>
        <StoryRing enabled state="unviewed" onOpen={() => {}} />
        <StoryRing enabled state="viewed" onOpen={() => {}} />
        <StoryRing enabled state="none" />
      </StateGroup>
      <StateGroup name="larger sizes" row>
        <StoryRing enabled state="unviewed" size="md" onOpen={() => {}} />
        <StoryRing enabled state="viewed" size="lg" onOpen={() => {}} />
      </StateGroup>
    </StatePanel>
  ),
};
