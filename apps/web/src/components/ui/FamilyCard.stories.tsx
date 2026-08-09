import type { Meta, StoryObj } from "@storybook/nextjs";

import { FamilyCard } from "./FamilyCard";
import { SAMPLE, StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Sitara/FamilyCard",
  component: FamilyCard,
  args: { name: SAMPLE.name, relation: SAMPLE.relation, city: SAMPLE.city },
} satisfies Meta<typeof FamilyCard>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Complete: Story = {
  args: { upcoming: SAMPLE.date, languageLabel: "हिन्दी", onOpen: () => {} },
};
/** Incomplete is normal, not an error — a neutral chip, never a caution colour. */
export const WithoutBirthDetails: Story = { args: { hasBirthDetails: false } };
export const Minimal: Story = { args: { city: undefined } };

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="complete · missing birth details · minimal">
        <FamilyCard
          name={SAMPLE.name}
          relation={SAMPLE.relation}
          city={SAMPLE.city}
          upcoming={SAMPLE.date}
          languageLabel="हिन्दी"
          onOpen={() => {}}
        />
        <FamilyCard
          name={SAMPLE.name}
          relation={SAMPLE.relation}
          city={SAMPLE.city}
          hasBirthDetails={false}
        />
        <FamilyCard name={SAMPLE.name} relation={SAMPLE.relation} />
      </StateGroup>
    </StatePanel>
  ),
};
