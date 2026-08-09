import type { Meta, StoryObj } from "@storybook/nextjs";

import { PaywallPanel } from "./PaywallPanel";
import { PriceCard } from "./PriceCard";
import { StateGroup, StatePanel } from "./_story-utils";

const RECAP = [
  "42 memories Tara is holding for you",
  "Your chart, computed exactly — your birth time is precise",
  "128 mornings together",
];

const PLANS = (
  <>
    <PriceCard
      planLabel="Annual"
      price="₹3,999"
      periodLabel="per year"
      totalWithTax="₹4,719"
      savingsLabel="₹1,989 less than monthly"
      selected
    />
    <PriceCard planLabel="Monthly" price="₹499" periodLabel="per month" totalWithTax="₹589" />
  </>
);

const meta = {
  title: "Feedback/PaywallPanel",
  component: PaywallPanel,
  args: {
    open: true,
    onClose: () => {},
    valueRecap: RECAP,
    children: PLANS,
    onContinue: () => {},
  },
  parameters: {
    layout: "fullscreen",
    docs: {
      description: {
        component:
          "S31 / §0.9 invitation register. The §29.2 dark-pattern checklist is the API contract: no countdown, no guilt copy, close always visible, price incl. tax before the rail. The recap is personalised from HER data — the honest reason to continue, not manufactured urgency.",
      },
    },
  },
} satisfies Meta<typeof PaywallPanel>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Open: Story = {};
export const WithGiftAndRestore: Story = {
  args: { onOpenGift: () => {}, onRestorePurchase: () => {} },
};
export const Busy: Story = { args: { busy: true } };

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="the invitation — close is always visible">
        <div className="relative min-h-[42rem]">
          <PaywallPanel
            open
            onClose={() => {}}
            valueRecap={RECAP}
            onContinue={() => {}}
            onOpenGift={() => {}}
            onRestorePurchase={() => {}}
          >
            {PLANS}
          </PaywallPanel>
        </div>
      </StateGroup>
    </StatePanel>
  ),
};
