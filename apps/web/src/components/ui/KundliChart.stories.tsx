import type { Meta, StoryObj } from "@storybook/nextjs";
import { useState } from "react";

import { KundliChart, type KundliHouse, type KundliStyle } from "./KundliChart";
import { StateGroup, StatePanel } from "./_story-utils";

/**
 * Fixed sample placements so screenshots stay byte-stable. These stand in for
 * M2 chart facts — the component never computes them (§5.3).
 */
const HOUSES: KundliHouse[] = [
  { house: 1, rashi: 9, grahas: ["jupiter"], isLagna: true },
  { house: 2, rashi: 10, grahas: [] },
  { house: 3, rashi: 11, grahas: ["saturn"] },
  { house: 4, rashi: 12, grahas: ["ketu"] },
  { house: 5, rashi: 1, grahas: [] },
  { house: 6, rashi: 2, grahas: ["mars"] },
  { house: 7, rashi: 3, grahas: [] },
  { house: 8, rashi: 4, grahas: [] },
  { house: 9, rashi: 5, grahas: ["sun", "mercury", "venus"] },
  { house: 10, rashi: 6, grahas: ["rahu"] },
  { house: 11, rashi: 7, grahas: ["moon"] },
  { house: 12, rashi: 8, grahas: [] },
];

const meta = {
  title: "Sitara/KundliChart",
  component: KundliChart,
  args: { houses: HOUSES, style: "north" },
  parameters: {
    docs: {
      description: {
        component:
          "Added by CC-007, taking the §24.3 library to 49; **the diagram itself landed in M10**, changing the render and not the interface. North Indian diamond is the default and South Indian square the user-switchable variant, and they are not alternate skins: north fixes the HOUSES on the page and moves the rashis, south fixes the RASHIS and moves the houses, so each places by a different key (`kundli-geometry.ts`). Placements arrive as M2 engine facts already resolved by the caller — §5.3 forbids computing them here — and §5.4's confidence renders ON the artefact, because a diamond drawn from a guessed ascendant is a confident-looking lie. The glyphs in the boxes are script-aware abbreviations, as on paper; the full names are in the list beneath.",
      },
    },
  },
} satisfies Meta<typeof KundliChart>;

export default meta;
type Story = StoryObj<typeof meta>;

export const NorthIndian: Story = { args: { style: "north" } };
export const SouthIndian: Story = { args: { style: "south" } };
export const Switchable: Story = { args: { onStyleChange: () => {} } };
/** §5.4 — a chart drawn from a birth-time window says so. */
export const ApproximateBirthTime: Story = { args: { confidence: "approximate" } };
/** Moon-chart mode: no lagna, so the diagram cannot claim one. */
export const MoonChartMode: Story = {
  args: {
    confidence: "tradition_based_general",
    houses: HOUSES.map((h) => ({ ...h, isLagna: false })),
  },
};

export const Interactive: Story = {
  render: function InteractiveDemo() {
    const [style, setStyle] = useState<KundliStyle>("north");
    return <KundliChart houses={HOUSES} style={style} onStyleChange={setStyle} />;
  },
};

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="north (default) · switchable · south">
        <KundliChart houses={HOUSES} style="north" />
        <KundliChart houses={HOUSES} style="south" onStyleChange={() => {}} />
      </StateGroup>
      <StateGroup name="§5.4 confidence — approximate time · Moon-chart mode">
        <KundliChart houses={HOUSES} confidence="approximate" />
        <KundliChart
          houses={HOUSES.map((h) => ({ ...h, isLagna: false }))}
          confidence="tradition_based_general"
        />
      </StateGroup>
    </StatePanel>
  ),
};
