import type { Meta, StoryObj } from "@storybook/nextjs";

import { ConsentRow } from "./ConsentRow";
import { SAMPLE, StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Feedback/ConsentRow",
  component: ConsentRow,
  args: {
    labelKey: "ui.notif.class.marketing",
    granted: true,
    grantedOn: SAMPLE.date,
    policyVersion: "3.7",
    onChange: () => {},
  },
  parameters: {
    docs: {
      description: {
        component:
          "A ledger row is a record, not a control: what was agreed, when, and against which policy version. Where consent is required for the service to exist, that is said in words rather than shown as a dead switch.",
      },
    },
  },
} satisfies Meta<typeof ConsentRow>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Granted: Story = {};
export const Withdrawn: Story = { args: { granted: false } };
export const Required: Story = { args: { required: true } };

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="granted · withdrawn · required (explained, not disabled)">
        <ConsentRow
          labelKey="ui.notif.class.marketing"
          descriptionKey="ui.consent.read_policy"
          granted
          grantedOn={SAMPLE.date}
          policyVersion="3.7"
          onChange={() => {}}
          onOpenPolicy={() => {}}
        />
        <ConsentRow
          labelKey="ui.notif.class.conversational"
          granted={false}
          policyVersion="3.7"
          onChange={() => {}}
        />
        <ConsentRow
          labelKey="ui.notif.class.transactional"
          descriptionKey="ui.notif.always_on"
          granted
          grantedOn={SAMPLE.date}
          policyVersion="3.7"
          required
          onOpenPolicy={() => {}}
        />
      </StateGroup>
    </StatePanel>
  ),
};
