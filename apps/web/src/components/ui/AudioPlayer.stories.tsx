import type { Meta, StoryObj } from "@storybook/nextjs";

import { AudioPlayer } from "./AudioPlayer";
import { StateGroup, StatePanel } from "./_story-utils";

const meta = {
  title: "Feedback/AudioPlayer",
  component: AudioPlayer,
  args: {
    playing: false,
    onTogglePlay: () => {},
    progress: 0.35,
    elapsed: "0:42",
    duration: "2:04",
    onOpenTranscript: () => {},
  },
  parameters: {
    docs: {
      description: {
        component:
          "The morning-brief player (S14). The transcript is a peer of the audio, not a hidden fallback — listening and reading are both first-class. Briefs are listen-only (§27): no download control.",
      },
    },
  },
} satisfies Meta<typeof AudioPlayer>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Paused: Story = {};
export const Playing: Story = { args: { playing: true, progress: 0.62, elapsed: "1:17" } };
/** Synthesis failed — and the text brief still works, which the copy says. */
export const Unavailable: Story = { args: { unavailable: true } };

export const AllStates: Story = {
  render: () => (
    <StatePanel>
      <StateGroup name="paused · playing · at the start · unavailable">
        <AudioPlayer
          playing={false}
          onTogglePlay={() => {}}
          progress={0.35}
          elapsed="0:42"
          duration="2:04"
          onOpenTranscript={() => {}}
        />
        <AudioPlayer
          playing
          onTogglePlay={() => {}}
          progress={0.62}
          elapsed="1:17"
          duration="2:04"
          onOpenTranscript={() => {}}
        />
        <AudioPlayer
          playing={false}
          onTogglePlay={() => {}}
          progress={0}
          elapsed="0:00"
          duration="2:04"
        />
        <AudioPlayer
          playing={false}
          onTogglePlay={() => {}}
          progress={0}
          elapsed="0:00"
          duration="0:00"
          unavailable
        />
      </StateGroup>
    </StatePanel>
  ),
};
