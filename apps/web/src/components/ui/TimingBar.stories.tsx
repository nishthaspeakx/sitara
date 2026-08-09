import type { Meta, StoryObj } from "@storybook/nextjs";

import { TimingBar, type TimingBand } from "./TimingBar";
import { SAMPLE, StateGroup, StatePanel } from "./_story-utils";

const BANDS: TimingBand[] = [
  { label: "Amrit", startMinute: 372, endMinute: 468, quality: "favourable", range: "06:12 – 07:48" },
  { label: "Kaal", startMinute: 468, endMinute: 564, quality: "care", range: "07:48 – 09:24" },
  { label: "Shubh", startMinute: 564, endMinute: 660, quality: "favourable", range: "09:24 – 11:00" },
  { label: "Rahu Kaal", startMinute: 900, endMinute: 990, quality: "care", range: "15:00 – 16:30" },
  { label: "Char", startMinute: 990, endMinute: 1124, quality: "neutral", range: "16:30 – 18:44" },
];

const meta = {
  title: "Sitara/TimingBar",
  component: TimingBar,
  args: { bands: BANDS, nowMinute: 620, placeLabel: SAMPLE.city },
  parameters: {
    docs: {
      description: {
        component:
          "§29.4 — auspicious and care are NEVER encoded by colour alone. Every band carries its glyph (⬆ / ⚠) and its legend row, so the bar reads identically in greyscale and to a screen reader. Care is amber, never red.",
      },
    },
  },
} satisfies Meta<typeof TimingBar>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const WithoutNowMarker: Story = { args: { nowMinute: undefined } };
export const FavourableOnly: Story = {
  args: { bands: BANDS.filter((b) => b.quality === "favourable") },
};

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="full day with the now-marker, computed for a stated city (§30.2)">
        <TimingBar bands={BANDS} nowMinute={620} placeLabel={SAMPLE.city} />
      </StateGroup>
      <StateGroup name="no now-marker, no place">
        <TimingBar bands={BANDS} />
      </StateGroup>
    </StatePanel>
  ),
};
