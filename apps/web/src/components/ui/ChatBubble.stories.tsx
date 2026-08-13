import type { Meta, StoryObj } from "@storybook/nextjs";

import { ChatBubble } from "./ChatBubble";
import { VoiceNoteBubble } from "./VoiceNoteBubble";
import { SAMPLE, StateGroup, StatePanel } from "./_story-utils";

const CITED = [
  "Today the Moon moves through your ",
  { spanId: "s1", text: "tenth house" },
  ", so work themes rise before noon.",
];

const meta = {
  title: "Sitara/ChatBubble",
  component: ChatBubble,
  args: { author: "tara", content: CITED, timestamp: "07:04", onOpenTrust: () => {} },
  parameters: {
    docs: {
      description: {
        component:
          "WhatsApp grammar (§29.5): her photo lives in the header, never on every bubble. A cited span carries a message-local spanId — fact IDs stay internal (§30.4).",
      },
    },
  },
} satisfies Meta<typeof ChatBubble>;

export default meta;
type Story = StoryObj<typeof meta>;

export const FromTara: Story = {};
export const FromUser: Story = {
  args: { author: "user", content: [SAMPLE.transcript], onOpenTrust: undefined },
};
export const Failed: Story = {
  args: { author: "user", content: [SAMPLE.transcript], failed: true, onRetry: () => {} },
};

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="a thread — user, Tara with a citation, audio, failed send">
        <ChatBubble author="user" content={[SAMPLE.transcript]} timestamp="07:03" />
        <ChatBubble author="tara" content={CITED} timestamp="07:04" onOpenTrust={() => {}} />
        <ChatBubble
          author="tara"
          content={[]}
          timestamp="07:05"
          audio={
            <VoiceNoteBubble
              src={"data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAgD4AAAB9AAACABAAZGF0YQAAAAA="}
              mode="idle"
              duration="0:12"
              speed={1}
              transcriptStatus="ready"
              transcript={SAMPLE.transcript}
            />
          }
        />
        <ChatBubble
          author="user"
          content={[]}
          timestamp="07:05"
          audio={
            <VoiceNoteBubble
              src={"data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAgD4AAAB9AAACABAAZGF0YQAAAAA="}
              mode="idle"
              duration="0:08"
              speed={1}
              transcriptStatus="pending"
              expiresOn={SAMPLE.date}
            />
          }
        />
        <ChatBubble
          author="user"
          content={[SAMPLE.transcript]}
          timestamp="07:06"
          failed
          onRetry={() => {}}
        />
      </StateGroup>
    </StatePanel>
  ),
};
