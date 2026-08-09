import type { Meta, StoryObj } from "@storybook/nextjs";

import { Card } from "./Card";
import { SAMPLE, StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Structure/Card",
  component: Card,
  args: { children: <p className="text-body">{SAMPLE.factLine}</p> },
} satisfies Meta<typeof Card>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const Sunken: Story = { args: { tone: "sunken" } };
/** Deep navy for sky/ceremony moments (§0.13). */
export const Ceremony: Story = { args: { tone: "ceremony" } };
export const Tappable: Story = { args: { onClick: () => {} } };
/** §0.13 — reading surfaces target ≤65 characters per line. */
export const Measured: Story = { args: { measure: true } };

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="default · sunken · ceremony">
        <Card>
          <p className="text-body">{SAMPLE.factLine}</p>
        </Card>
        <Card tone="sunken">
          <p className="text-body">{SAMPLE.factLine}</p>
        </Card>
        <Card tone="ceremony">
          <p className="text-body">{SAMPLE.factLine}</p>
        </Card>
      </StateGroup>
      <StateGroup name="tappable · measured to 65ch">
        <Card onClick={() => {}}>
          <p className="text-body">{SAMPLE.factLine}</p>
        </Card>
        <Card measure>
          <p className="text-body">
            {SAMPLE.plainLanguage} {SAMPLE.factLine}
          </p>
        </Card>
      </StateGroup>
    </StatePanel>
  ),
};
