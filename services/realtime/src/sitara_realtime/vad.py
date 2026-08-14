"""Server-side voice activity detection (§25.3).

§25.3 says "barge-in = just speak (server-side VAD ducking)". Both halves of
that are decisions, not phrasing:

- **just speak** — there is no interrupt button, so the only signal available
  is the microphone itself.
- **server-side** — the detection happens where the PCM already is, on the way
  past. A client-side detector would put the decision in the one place a user
  can have a stale build of, and a barge-in that only some clients perform is a
  feature that works for some people.

What this does NOT do
---------------------

It does not segment utterances. The recogniser does that — Ink emits interim
and final results, and a final IS the turn. A second segmenter here would be a
second opinion about where a sentence ended, and the two would disagree exactly
on the hard cases (a pause mid-thought, a trailing "…so, yeah") that a
recogniser trained on speech handles better than a threshold on loudness.

So this answers one question: **is the user talking right now?** That is enough
for the two things §25.3 needs — ducking her audio when they start, and the
mic-live indicator — and it is a question energy can honestly answer where
"has this person finished their sentence" is not.

Why energy and not a model
---------------------------

A neural VAD would be better at a noisy kitchen. It would also be a model to
ship, warm and pay for in the one part of the path where §33.5 measures
latency, to make a decision whose cost of being wrong is that Tara keeps
talking for another 200 ms. The threshold is configurable so a real-world
false-trigger rate can move it; a model is the answer if that turns out not to
be enough, and it fits behind this same call.
"""

from __future__ import annotations

import array
import math
from dataclasses import dataclass

#: 16 kHz mono s16le, 20 ms per analysis frame — 320 samples. Short enough that
#: a barge-in feels immediate, long enough that one loud sample is not speech.
FRAME_SAMPLES = 320

#: RMS above which a frame counts as speech, in s16 units (full scale 32768).
#: ~1.5% of full scale: comfortably above room tone and mains hum, comfortably
#: below a person speaking at arm's length from a phone.
DEFAULT_SPEECH_RMS = 500.0

#: Consecutive speech frames before the detector says yes — 60 ms. This is the
#: whole defence against a cough, a door and a chair cutting Tara off
#: mid-sentence, and against her own voice leaking through a phone speaker into
#: its own microphone, which is the failure that makes a call unusable rather
#: than merely annoying.
DEFAULT_ONSET_FRAMES = 3

#: Consecutive quiet frames before it says no again — 500 ms. Longer than the
#: onset on purpose: the cost of ending a speech window early is clipping
#: someone mid-sentence, and the cost of ending it late is nothing at all.
DEFAULT_HANGOVER_FRAMES = 25


def rms(pcm: bytes) -> float:
    """Root-mean-square level of one 16-bit little-endian mono buffer."""
    if len(pcm) < 2:
        return 0.0
    samples = array.array("h")
    # An odd trailing byte is a truncated sample, not a quiet one. Dropping it
    # is right; letting `array` raise would take a call down over one byte.
    samples.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    if not samples:
        return 0.0
    total = 0
    for sample in samples:
        total += sample * sample
    return math.sqrt(total / len(samples))


@dataclass
class SpeechDetector:
    """Streaming, stateful, and cheap enough to run on every frame.

    `feed` returns the CURRENT speaking state rather than an edge, and callers
    watch for the transition themselves. An edge-returning API would have made
    "is the user still talking?" — which is what decides when to stop ducking —
    a question the caller had to track separately from the answer it was given.
    """

    speech_rms: float = DEFAULT_SPEECH_RMS
    onset_frames: int = DEFAULT_ONSET_FRAMES
    hangover_frames: int = DEFAULT_HANGOVER_FRAMES

    speaking: bool = False
    _loud: int = 0
    _quiet: int = 0

    def feed(self, pcm: bytes) -> bool:
        for offset in range(0, len(pcm) - 1, FRAME_SAMPLES * 2):
            frame = pcm[offset : offset + FRAME_SAMPLES * 2]
            if rms(frame) >= self.speech_rms:
                self._loud += 1
                self._quiet = 0
                if self._loud >= self.onset_frames:
                    self.speaking = True
            else:
                self._quiet += 1
                self._loud = 0
                if self._quiet >= self.hangover_frames:
                    self.speaking = False
        return self.speaking

    def reset(self) -> None:
        """After a barge-in has been acted on, so her next utterance is not cut
        by the tail of the speech that cut the last one."""
        self.speaking = False
        self._loud = 0
        self._quiet = 0
