import type { Meta, StoryObj } from "@storybook/nextjs";

import { FestivalBanner } from "./FestivalBanner";
import { StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Sitara/FestivalBanner",
  component: FestivalBanner,
  args: {
    name: "Pongal",
    traditionLabel: "as observed in Tamil Nadu",
    dateLabel: "14 January",
  },
  parameters: {
    docs: {
      description: {
        component:
          "The tradition is named, never assumed — Pongal and Uttarayan are the same date and different framings. Art is illustration, never sectarian imagery and never stock photography (§4.2, §24.7).",
      },
    },
  },
} satisfies Meta<typeof FestivalBanner>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const Tappable: Story = { args: { onOpen: () => {} } };

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="per-tradition framings of the same date">
        <FestivalBanner
          name="Pongal"
          traditionLabel="as observed in Tamil Nadu"
          dateLabel="14 January"
          onOpen={() => {}}
        />
        <FestivalBanner
          name="Uttarayan"
          traditionLabel="as observed in Gujarat"
          dateLabel="14 January"
          onOpen={() => {}}
        />
        <FestivalBanner
          name="Makar Sankranti"
          traditionLabel="as observed at home"
          dateLabel="14 January"
        />
      </StateGroup>
    </StatePanel>
  ),
};
