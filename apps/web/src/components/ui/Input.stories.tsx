import type { Meta, StoryObj } from "@storybook/nextjs";

import { Input } from "./Input";
import { StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Foundation/Input",
  component: Input,
  args: { labelKey: "auth.phone_label" },
} satisfies Meta<typeof Input>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Text: Story = { args: { kind: "text" } };
export const WithHelper: Story = { args: { helperKey: "auth.legal_hint" } };
export const WithError: Story = { args: { errorKey: "errors.auth.invalid_phone" } };
export const Otp: Story = { args: { kind: "otp", labelKey: "verify.code_label" } };

/** §29.4: 48px, label ABOVE (floating labels fail Indic scripts), error carries an icon. */
export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="text · date · time">
        <Input kind="text" labelKey="auth.phone_label" />
        <Input kind="date" labelKey="dob.label" />
        <Input kind="time" labelKey="ui.reflection.position" />
      </StateGroup>
      <StateGroup name="phone · otp">
        <Input kind="phone" labelKey="auth.phone_label" placeholder="+91 98765 43210" />
        <Input kind="otp" labelKey="verify.code_label" />
      </StateGroup>
      <StateGroup name="helper · error · disabled">
        <Input labelKey="auth.phone_label" helperKey="auth.legal_hint" />
        <Input labelKey="auth.phone_label" errorKey="errors.auth.invalid_phone" />
        <Input labelKey="auth.phone_label" disabled />
      </StateGroup>
    </StatePanel>
  ),
};
