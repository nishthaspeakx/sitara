"""§34.6's binary frame, and the two things done to it.

The wire format is fixed: 16 kHz mono PCM s16le, framed with an 8-byte header
(4-byte big-endian monotonic seq + 4-byte flags). Everything here is pure — no
network, no vendor, no clock — because frame reassembly is easy to get subtly
wrong and trivial to reproduce.

**Nothing transcodes.** §25.4 promises replay of "the user's ORIGINAL
recording", and the cheapest way to keep that true rather than nearly true is
for the stored bytes to be the received bytes. `pcm_to_wav` adds a 44-byte
header for vendors that want a container; it never touches a sample.
"""

from __future__ import annotations

import struct

from sitara_schemas import (
    BINARY_HEADER_BYTES,
    BINARY_SAMPLE_RATE_HZ,
    MAX_NOTE_DURATION_MS,
)

BYTES_PER_SAMPLE = 2  # s16le
_HEADER = struct.Struct(">II")  # seq, flags — big-endian per §34.6


class FrameError(ValueError):
    """A binary frame that cannot be trusted. Maps to SYS_VALIDATION.

    Loud rather than lenient: every failure below is a case where accepting the
    frame would produce a transcript of a sentence the user did not say.
    """


def parse_frame(frame: bytes) -> tuple[int, int, bytes]:
    """`(seq, flags, pcm)` from one §34.6 binary frame."""
    if len(frame) < BINARY_HEADER_BYTES:
        raise FrameError(f"frame shorter than the {BINARY_HEADER_BYTES}-byte header")
    seq, flags = _HEADER.unpack(frame[:BINARY_HEADER_BYTES])
    pcm = frame[BINARY_HEADER_BYTES:]
    if len(pcm) % BYTES_PER_SAMPLE:
        # A half sample means the frame was truncated in transit. Keeping it
        # would shift every subsequent sample by one byte and turn the rest of
        # the note into noise — which STT would transcribe as *something*.
        raise FrameError("frame payload is not a whole number of 16-bit samples")
    return seq, flags, pcm


def build_frame(seq: int, pcm: bytes, *, flags: int = 0) -> bytes:
    """The inverse, for the test harness and the recorder."""
    return _HEADER.pack(seq, flags) + pcm


class NoteAssembler:
    """Reassembles one held recording from its frames.

    Sequence gaps FAIL the note rather than concatenating across the hole.
    That is the whole reason this class exists: a note missing its middle still
    transcribes, and it transcribes into a fluent sentence the user never said —
    which then goes to §9 as their question and gets answered. Dropping the
    note and saying so is the honest failure; §28.3 already designs for it
    ("transcribe-fail → 'send as text?' original audio preserved").
    """

    def __init__(self, *, max_duration_ms: int = MAX_NOTE_DURATION_MS) -> None:
        self._chunks: list[bytes] = []
        self._next_seq = 0
        self._max_bytes = duration_to_bytes(max_duration_ms)

    def add(self, frame: bytes) -> None:
        seq, _flags, pcm = parse_frame(frame)
        if seq != self._next_seq:
            raise FrameError(
                f"frame {seq} arrived where {self._next_seq} was expected — a gap in "
                "a voice note transcribes into a sentence nobody said"
            )
        self._next_seq += 1
        self._chunks.append(pcm)
        if self.byte_length > self._max_bytes:
            raise FrameError(
                f"note exceeds the {MAX_NOTE_DURATION_MS} ms cap "
                f"({self._max_bytes} bytes); the client stops at the cap"
            )

    @property
    def byte_length(self) -> int:
        return sum(len(c) for c in self._chunks)

    @property
    def frame_count(self) -> int:
        return len(self._chunks)

    def pcm(self) -> bytes:
        return b"".join(self._chunks)


def duration_ms(pcm: bytes, sample_rate_hz: int = BINARY_SAMPLE_RATE_HZ) -> int:
    return int(len(pcm) / BYTES_PER_SAMPLE / sample_rate_hz * 1000)


def duration_to_bytes(ms: int, sample_rate_hz: int = BINARY_SAMPLE_RATE_HZ) -> int:
    return int(ms / 1000 * sample_rate_hz * BYTES_PER_SAMPLE)


def pcm_to_wav(pcm: bytes, sample_rate_hz: int = BINARY_SAMPLE_RATE_HZ) -> bytes:
    """A canonical 44-byte RIFF header in front of the samples.

    Written by hand rather than via `wave` so the output is byte-for-byte
    deterministic and the samples are provably untouched — `wave` would copy
    them through a file object to the same effect, with more to reason about.

    The sizes are REAL, unlike the streaming WAV Cartesia's TTS returns (which
    writes 0xFFFFFFFF for a length it does not know yet). A player seeking in a
    30-day-old note should not have to guess how long it is.
    """
    if len(pcm) % BYTES_PER_SAMPLE:
        raise FrameError("PCM payload is not a whole number of 16-bit samples")
    channels, bits = 1, 16
    byte_rate = sample_rate_hz * channels * bits // 8
    block_align = channels * bits // 8
    return b"".join(
        (
            b"RIFF",
            struct.pack("<I", 36 + len(pcm)),
            b"WAVEfmt ",
            struct.pack("<IHHIIHH", 16, 1, channels, sample_rate_hz, byte_rate, block_align, bits),
            b"data",
            struct.pack("<I", len(pcm)),
            pcm,
        )
    )


def wav_to_pcm(wav: bytes) -> tuple[bytes, int]:
    """`(pcm, sample_rate_hz)` from a RIFF/WAVE payload.

    Used by the fixture recorder to feed Sonic's output back into Ink. It walks
    the chunk list rather than assuming the data starts at byte 44: Cartesia's
    TTS emits a `LIST`/`INFO` chunk before `data`, so the fixed-offset version
    of this function silently transcribed the metadata as audio.
    """
    if len(wav) < 12 or wav[:4] != b"RIFF" or wav[8:12] != b"WAVE":
        raise FrameError("not a RIFF/WAVE payload")
    sample_rate = BINARY_SAMPLE_RATE_HZ
    offset = 12
    while offset + 8 <= len(wav):
        chunk_id = wav[offset : offset + 4]
        (size,) = struct.unpack("<I", wav[offset + 4 : offset + 8])
        body = offset + 8
        if chunk_id == b"fmt " and body + 16 <= len(wav):
            sample_rate = struct.unpack("<I", wav[body + 4 : body + 8])[0]
        elif chunk_id == b"data":
            # A streaming WAV writes 0xFFFFFFFF here; take what is actually
            # present rather than trusting a length the encoder never knew.
            end = len(wav) if size in (0xFFFFFFFF, 0) else min(body + size, len(wav))
            return wav[body:end], sample_rate
        offset = body + size + (size % 2)
    raise FrameError("RIFF payload has no data chunk")
