import type { Meta, StoryObj } from "@storybook/nextjs";

import { TrustSheet } from "./TrustSheet";
import { SAMPLE, StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Sitara/TrustSheet",
  component: TrustSheet,
  args: {
    open: true,
    onClose: () => {},
    plainLanguage: SAMPLE.plainLanguage,
    confidence: "verified",
    detailLines: [...SAMPLE.detailLines],
  },
  parameters: {
    layout: "fullscreen",
    docs: {
      description: {
        component:
          "THE canonical component — WhyThisSheet is retired (§34.7). Three layers per §30.4: plain language, the sources row, the details expander. It has no prop that can carry a fact ID, because §30.4 keeps those internal and never renders them to users.",
      },
    },
  },
} satisfies Meta<typeof TrustSheet>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Layer 1 + 2 only. */
export const LayersOneAndTwo: Story = { args: { detailLines: [] } };
/** Layer 3 collapsed — the expander is present but closed. */
export const DetailsCollapsed: Story = {};
/** Layer 3 open, showing readable terms rather than fact IDs. */
export const DetailsExpanded: Story = { args: { defaultExpanded: true } };
export const SingleSource: Story = {
  args: { confidence: "verified_limited", sourceState: "single" },
};
export const Disputed: Story = {
  args: { confidence: "approximate", sourceState: "disputed" },
};
export const CannotCalculate: Story = {
  args: { confidence: "cannot_calculate", sourceState: "single", detailLines: [] },
};

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="all three layers, expanded (§30.4)">
        <div className="relative min-h-[32rem]">
          <TrustSheet
            open
            onClose={() => {}}
            plainLanguage={SAMPLE.plainLanguage}
            confidence="verified"
            detailLines={[...SAMPLE.detailLines]}
            defaultExpanded
          />
        </div>
      </StateGroup>
    </StatePanel>
  ),
};
