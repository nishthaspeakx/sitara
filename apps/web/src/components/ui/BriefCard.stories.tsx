import { MORNING_MODULES } from "@sitara/schemas";
import type { Meta, StoryObj } from "@storybook/nextjs";

import { BriefCard } from "./BriefCard";
import { RatingTap } from "./RatingTap";
import { SAMPLE, StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Sitara/BriefCard",
  component: BriefCard,
  args: { module: "energy_of_day", factLine: SAMPLE.factLine },
  parameters: {
    docs: {
      description: {
        component:
          "ONE master, 17 module variants (§7.1/§34.3 closed set). `module` is typed MorningModule, so a card cannot render an id the ranking engine may not emit.",
      },
    },
  },
} satisfies Meta<typeof BriefCard>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Core: Story = { args: { emphasis: "core", confidence: "verified" } };
export const Contextual: Story = { args: { confidence: "approximate" } };
export const WithWhyThis: Story = {
  args: { confidence: "verified", onWhyThis: () => {} },
};
export const Locked: Story = { args: { locked: true } };

/** All 17 modules — the icon slot and title of every one the engine can emit. */
export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="core emphasis · contextual · locked (free tier)">
        <BriefCard
          module="energy_of_day"
          factLine={SAMPLE.factLine}
          emphasis="core"
          confidence="verified"
          onWhyThis={() => {}}
          actions={<RatingTap onRate={() => {}} />}
        />
        <BriefCard
          module="favourable_window"
          factLine={SAMPLE.factLine}
          confidence="verified_limited"
          onWhyThis={() => {}}
        />
        <BriefCard module="work" factLine={SAMPLE.factLine} locked />
      </StateGroup>
      <StateGroup name="the 17 morning modules (§7.1 / §34.3)">
        {MORNING_MODULES.map((module) => (
          <BriefCard key={module} module={module} factLine={SAMPLE.factLine} />
        ))}
      </StateGroup>
    </StatePanel>
  ),
};
