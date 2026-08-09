import type { Meta, StoryObj } from "@storybook/nextjs";

import { PriceCard } from "./PriceCard";
import { StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Feedback/PriceCard",
  component: PriceCard,
  args: {
    planLabel: "Annual",
    price: "₹3,999",
    periodLabel: "per year",
    totalWithTax: "₹4,719",
  },
  parameters: {
    docs: {
      description: {
        component:
          "§30.3 acceptance: the total INCLUDING TAX is shown before the payment rail, and savings are stated plainly. There is no countdown prop, no 'only today' prop and no strikethrough-anchor prop — the component cannot express a dark pattern (§29.2).",
      },
    },
  },
} satisfies Meta<typeof PriceCard>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Annual: Story = { args: { selected: true, savingsLabel: "₹1,989 less than monthly" } };
export const Monthly: Story = {
  args: { planLabel: "Monthly", price: "₹499", periodLabel: "per month", totalWithTax: "₹589" },
};
export const FoundingOffer: Story = { args: { foundingOffer: true } };

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="selected · unselected · founding offer">
        <PriceCard
          planLabel="Annual"
          price="₹3,999"
          periodLabel="per year"
          totalWithTax="₹4,719"
          savingsLabel="₹1,989 less than monthly"
          selected
        />
        <PriceCard
          planLabel="Monthly"
          price="₹499"
          periodLabel="per month"
          totalWithTax="₹589"
        />
        <PriceCard
          planLabel="Annual"
          price="$99"
          periodLabel="per year"
          totalWithTax="$99"
          foundingOffer
        />
      </StateGroup>
    </StatePanel>
  ),
};
