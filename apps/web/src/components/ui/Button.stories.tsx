import type { Meta, StoryObj } from "@storybook/nextjs";

import { Button } from "./Button";
import { StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Foundation/Button",
  component: Button,
  args: { children: "Continue" },
} satisfies Meta<typeof Button>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Primary: Story = { args: { variant: "primary" } };
export const Secondary: Story = { args: { variant: "secondary" } };
export const Tertiary: Story = { args: { variant: "tertiary" } };
export const Loading: Story = { args: { loading: true } };
export const Disabled: Story = { args: { disabled: true } };

/** §24.3: primary/secondary/tertiary × default·pressed·loading·disabled. */
export const AllStates: Story = {
  render: () => (
    <StatePanel>
      {(["primary", "secondary", "tertiary"] as const).map((variant) => (
        <StateGroup key={variant} name={variant} row>
          <Button variant={variant}>Continue</Button>
          {/* pressed is rendered, not described — and each variant's pressed fill
              is its own: gold darkens, the outline/text variants sink */}
          <Button
            variant={variant}
            className={variant === "primary" ? "bg-interactive-pressed" : "bg-surface-sunken"}
          >
            Continue
          </Button>
          <Button variant={variant} loading>
            Continue
          </Button>
          <Button variant={variant} disabled>
            Continue
          </Button>
        </StateGroup>
      ))}
      <StateGroup name="full width">
        <Button fullWidth>Meet your mornings</Button>
      </StateGroup>
    </StatePanel>
  ),
};
