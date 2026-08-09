import type { Meta, StoryObj } from "@storybook/nextjs";
import { Settings } from "lucide-react";

import { Header } from "./Header";
import { IconButton } from "./IconButton";
import { ICON_STROKE } from "./_util";
import { SAMPLE, StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Structure/Header",
  component: Header,
  args: { variant: "titled", titleKey: "ui.tabs.today" },
} satisfies Meta<typeof Header>;

export default meta;
type Story = StoryObj<typeof meta>;

/** §24.1 — the portrait chip is persistent on Today and Ask Tara, and only there. */
export const Presence: Story = { args: { variant: "presence" } };
export const PresenceExpanded: Story = {
  args: { variant: "presence", taraExpanded: true, taraState: "listening" },
};
export const Titled: Story = { args: { variant: "titled", onBack: () => {} } };
export const Bare: Story = { args: { variant: "bare", onBack: () => {} } };

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="presence — collapsed 56px, expands on voice/ceremony (§24.1)"> {/* token-lint-disable-line — spec citation in a story label */}
        <Header variant="presence" titleKey="ui.tabs.today" />
        <Header
          variant="presence"
          titleKey="ui.tabs.ask"
          taraExpanded
          taraState="listening"
          actions={
            <IconButton labelKey="ui.close" icon={<Settings strokeWidth={ICON_STROKE} />} />
          }
        />
      </StateGroup>
      <StateGroup name="titled — with back, with user data as the title">
        <Header variant="titled" titleKey="ui.tabs.journal" onBack={() => {}} />
        <Header
          variant="titled"
          title={SAMPLE.name}
          subtitleKey="ui.family.upcoming"
          onBack={() => {}}
        />
      </StateGroup>
      <StateGroup name="bare — onboarding and ceremony screens carry no chrome">
        <Header variant="bare" onBack={() => {}} />
      </StateGroup>
    </StatePanel>
  ),
};
