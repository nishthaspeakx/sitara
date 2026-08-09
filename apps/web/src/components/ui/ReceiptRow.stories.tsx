import type { Meta, StoryObj } from "@storybook/nextjs";

import { ReceiptRow } from "./ReceiptRow";
import { SAMPLE, StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Feedback/ReceiptRow",
  component: ReceiptRow,
  args: {
    description: "Sitara annual",
    amount: "₹4,719",
    date: SAMPLE.date,
    status: "paid",
  },
  parameters: {
    docs: {
      description: {
        component:
          "§30.3 — a pending UPI mandate is not an error and does not borrow the error colour; a failure states its mapped plain-language reason rather than a code. Amounts stay in the transaction's own currency (§30.3 never converts mid-cycle).",
      },
    },
  },
} satisfies Meta<typeof ReceiptRow>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Paid: Story = { args: { onOpenInvoice: () => {} } };
export const Pending: Story = { args: { status: "pending" } };
export const Failed: Story = {
  args: { status: "failed", reason: "Your bank declined the mandate. You can try another method." },
};
export const Refunded: Story = { args: { status: "refunded" } };

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="paid · pending · failed · refunded">
        <ReceiptRow
          description="Sitara annual"
          amount="₹4,719"
          date={SAMPLE.date}
          status="paid"
          onOpenInvoice={() => {}}
        />
        <ReceiptRow
          description="Sitara monthly"
          amount="₹589"
          date={SAMPLE.date}
          status="pending"
        />
        <ReceiptRow
          description="Sitara monthly"
          amount="₹589"
          date={SAMPLE.date}
          status="failed"
          reason="Your bank declined the mandate. You can try another method."
        />
        <ReceiptRow
          description="Sitara annual"
          amount="₹4,719"
          date={SAMPLE.date}
          status="refunded"
        />
      </StateGroup>
    </StatePanel>
  ),
};
