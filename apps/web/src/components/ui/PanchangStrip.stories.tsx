import type { Meta, StoryObj } from "@storybook/nextjs";

import { PanchangStrip, type PanchangEntry } from "./PanchangStrip";
import { StateGroup, StatePanel } from "./_story-utils";

const ENTRIES: PanchangEntry[] = [
  { labelKey: "ui.panchang.tithi", value: "Shukla Dashami" },
  { labelKey: "ui.panchang.nakshatra", value: "Purva Bhadrapada" },
  { labelKey: "ui.panchang.yoga", value: "Siddhi" },
  { labelKey: "ui.panchang.karana", value: "Taitila" },
];

const meta = {
  title: "Sitara/PanchangStrip",
  component: PanchangStrip,
  args: { entries: ENTRIES },
} satisfies Meta<typeof PanchangStrip>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const Short: Story = { args: { entries: ENTRIES.slice(0, 2) } };
/** The almanac not arriving is said plainly, not hidden behind an empty strip. */
export const Unavailable: Story = { args: { unavailable: true } };

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="full strip — wraps 2×2 at 320px (§29.3)"> {/* token-lint-disable-line — spec citation in a story label */}
        <PanchangStrip entries={ENTRIES} />
      </StateGroup>
      <StateGroup name="partial">
        <PanchangStrip entries={ENTRIES.slice(0, 2)} />
      </StateGroup>
      <StateGroup name="unavailable">
        <PanchangStrip entries={[]} unavailable />
      </StateGroup>
    </StatePanel>
  ),
};
