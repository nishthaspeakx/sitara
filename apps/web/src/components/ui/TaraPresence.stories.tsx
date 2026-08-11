import type { Meta, StoryObj } from "@storybook/nextjs";

import { TaraPresence } from "./TaraPresence";
import { TARA_SIZES, PRESENCE_STATES } from "./_util";
import { StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Sitara/TaraPresence",
  component: TaraPresence,
  args: { size: "md", state: "profile_portrait" },
  parameters: {
    docs: {
      description: {
        component:
          "Tara's likeness is AI-generated and exclusively owned by Sitara — she is not a real person and not a licensed human model (CC-008, superseding §25.2's baseline). The permanent 'Tara · AI guide' disclosure is mandatory wherever her name or face appears. The delivered kit is stills only, so no loop is mounted; asset paths live only in tara-assets.ts, and two states (concern_kind, safety_still) are flagged there as approximate frames pending a purpose-shot round.",
      },
    },
  },
} satisfies Meta<typeof TaraPresence>;

export default meta;
type Story = StoryObj<typeof meta>;

export const HeaderChip: Story = { args: { size: "sm" } };
export const WithDisclosure: Story = { args: { size: "md", showAiLabel: true } };
export const Night: Story = { args: { size: "lg", state: "night" } };
/** Reduced motion never mounts the loop — the poster IS the component. */
export const Still: Story = { args: { size: "lg", still: true } };

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="sizes (full is the call layout, sized by its container)" row>
        {TARA_SIZES.filter((s) => s !== "full").map((size) => (
          <TaraPresence key={size} size={size} state="profile_portrait" />
        ))}
      </StateGroup>
      <StateGroup name="the 12 presence states (§4.3)" row>
        {PRESENCE_STATES.map((state) => (
          <TaraPresence key={state} size="sm" state={state} />
        ))}
      </StateGroup>
      <StateGroup name="§25.2 disclosure — permanent wherever her name appears" row>
        <TaraPresence size="md" state="welcome" showAiLabel />
      </StateGroup>
    </StatePanel>
  ),
};
