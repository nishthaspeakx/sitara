import type { Meta, StoryObj } from "@storybook/nextjs";

import { ErrorState, type ErrorEnvelope } from "./ErrorState";
import { SAMPLE, StateGroup, StatePanel } from "./_story-utils";

const RETRYABLE: ErrorEnvelope = {
  code: "ASTRO_ENGINE_UNAVAILABLE",
  message_key: "errors.astro.engine_unavailable",
  trace_id: SAMPLE.traceId,
  retryable: true,
};

const TERMINAL: ErrorEnvelope = {
  code: "ASTRO_INSUFFICIENT_BIRTH_DATA",
  message_key: "errors.astro.insufficient_birth_data",
  trace_id: SAMPLE.traceId,
  retryable: false,
};

const meta = {
  title: "Feedback/ErrorState",
  component: ErrorState,
  args: { error: RETRYABLE, onRetry: () => {} },
  parameters: {
    docs: {
      description: {
        component:
          "Takes a §34.4 envelope, not a string: message_key renders through the catalogs so there is never an English error in a Hindi session, and `retryable` decides whether the retry control exists — an unretryable failure must not offer a button that cannot work.",
      },
    },
  },
} satisfies Meta<typeof ErrorState>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Retryable: Story = {};
/** No retry control at all — the envelope says it cannot help. */
export const NotRetryable: Story = { args: { error: TERMINAL } };
export const Fatal: Story = {
  args: { fatal: true, statusHref: "https://status.sitara.app" },
};

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="retryable · not retryable · fatal (S46)">
        <ErrorState error={RETRYABLE} onRetry={() => {}} />
        <ErrorState error={TERMINAL} onRetry={() => {}} />
        <ErrorState
          error={RETRYABLE}
          onRetry={() => {}}
          fatal
          statusHref="https://status.sitara.app"
        />
      </StateGroup>
    </StatePanel>
  ),
};
