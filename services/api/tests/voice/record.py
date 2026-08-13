"""Record the Cartesia fixtures, and measure the round-trip honestly.

    CARTESIA_API_KEY=... uv run python -m tests.voice.record

Same discipline as `tests/memory/crosslingual/record.py`: the suite must never
depend on a live vendor, so what CI replays is recorded once, deliberately, by
a person who looked at the result.

What this measures, and what it does NOT
----------------------------------------

It synthesises each utterance with Sonic, feeds the audio back through Ink, and
compares the transcript to the text it started from. That is a **synthetic
round-trip**, and the distinction matters most exactly where the product does:

Sonic's output is clean, evenly paced, correctly stressed studio speech. Real
voice notes are a phone in a kitchen, an accent, a false start, a word swallowed
halfway. So a WER measured here is a FLOOR on the error rate, not an estimate of
it — the number will be better than the product's, and most flatteringly so for
Hinglish, where the hard part is a real speaker's spontaneous code-switching
rather than a synthesiser's rendering of pre-mixed text.

§3.2's acceptance gate is scored by a native panel on real speech (§3.4's
corpus). Nothing this script prints is that gate, and nothing here should be
quoted as though it were.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from sitara_api.voice.audio import wav_to_pcm
from sitara_api.voice.providers.base import (
    SynthesisRequest,
    TranscriptionRequest,
    stt_language_for,
)
from sitara_api.voice.providers.cartesia import CartesiaSttProvider, CartesiaTtsProvider

FIXTURES = Path(__file__).parent / "fixtures"

#: Cartesia's public Hindi-capable voice. Not Tara's — §3.2's anchor artist is a
#: contracted clone that does not exist yet, and §26.2/CC-008 governs her
#: likeness. This is a bake-off instrument, not her voice.
BAKEOFF_VOICE_ID = "87748186-23bb-4158-a1eb-332911b0b708"


@dataclass(frozen=True)
class Utterance:
    """One line of the §3.4 corpus, in miniature.

    `locale` is a §2.4 locale, so the adapters do their own language mapping —
    which is the point: the mapping is what this exercises.
    """

    name: str
    locale: str
    text: str
    why: str


#: Three locales, chosen so each carries the thing that actually breaks in it.
CORPUS: tuple[Utterance, ...] = (
    Utterance(
        name="en",
        locale="en",
        text="What does my chart say about starting a new job on Monday?",
        why="the control — no script question, no code-mixing",
    ),
    Utterance(
        name="hi",
        locale="hi",
        text="मेरा राहु काल आज कब है, और क्या मुझे सोमवार को नया काम शुरू करना चाहिए?",
        why="Devanagari in, Devanagari out; carries two §3.4 astrology terms",
    ),
    Utterance(
        name="hi-Latn",
        locale="hi-Latn",
        text="Mera rahu kaal kab hai aaj, and should I start the new job on Monday?",
        why=(
            "the case that matters: 40-60% English tokens mid-sentence (§3.3). "
            "Both the code-mixing AND the Latin script must survive"
        ),
    ),
)


# ---------------------------------------------------------------------------
# Scoring


def normalise(text: str) -> list[str]:
    """Tokens for comparison: NFC, casefolded, punctuation dropped.

    Punctuation is dropped because STT restores it by prosody and no product
    decision rides on a comma. Case is folded because Ink capitalises
    sentence-initially and "Mera"/"mera" is not an error a user would notice.
    """
    folded = unicodedata.normalize("NFC", text).casefold()
    words = (w for w in folded.split() if w)
    return ["".join(c for c in w if not unicodedata.category(c).startswith("P")) for w in words]


def wer(reference: str, hypothesis: str) -> tuple[float, int, int]:
    """Word error rate by Levenshtein distance over tokens.

    Returned with its operands, because a rate alone hides how few words it was
    computed over — 1 error in 12 is 8.3%, and quoting 8.3% without the 12 is
    how a sample of one sentence becomes a claim about a language.
    """
    ref, hyp = normalise(reference), normalise(hypothesis)
    if not ref:
        return 0.0, 0, 0
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i]
        for j, h in enumerate(hyp, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h)))
        prev = cur
    return prev[-1] / len(ref), prev[-1], len(ref)


def script_of(text: str) -> str:
    """`devanagari`, `latin`, or `mixed` — §2.4's actual question.

    A transcript can be word-perfect and still wrong for its locale: `hi-Latn`
    IS Hinglish, so Devanagari there is the §2.4 violation the locale exists to
    prevent, and no accuracy metric reports it.
    """
    scripts = set()
    for ch in text:
        if not ch.isalpha():
            continue
        name = unicodedata.name(ch, "")
        if "DEVANAGARI" in name:
            scripts.add("devanagari")
        elif "LATIN" in name:
            scripts.add("latin")
    if len(scripts) == 1:
        return scripts.pop()
    return "mixed" if scripts else "none"


EXPECTED_SCRIPT = {"en": "latin", "hi": "devanagari", "hi-Latn": "latin"}


@dataclass
class Row:
    utterance: Utterance
    transcript: str
    error_rate: float
    errors: int
    words: int
    script: str
    stt_language: str
    detected: str | None
    audio_bytes: int
    notes: list[str] = field(default_factory=list)

    @property
    def script_ok(self) -> bool:
        expected = EXPECTED_SCRIPT[self.utterance.locale]
        # Hinglish is legitimately mixed as WORDS; what must not appear is
        # Devanagari. "latin" and "mixed"-with-no-Devanagari both pass.
        if self.utterance.locale == "hi-Latn":
            return "devanagari" not in self.script
        return self.script in (expected, "mixed")


async def record() -> list[Row]:
    api_key = os.environ.get("CARTESIA_API_KEY", "")
    if not api_key:
        sys.exit("CARTESIA_API_KEY is not set")

    tts = CartesiaTtsProvider(api_key, voice_id=BAKEOFF_VOICE_ID, sample_rate_hz=16_000)
    stt = CartesiaSttProvider(api_key)
    FIXTURES.mkdir(parents=True, exist_ok=True)

    rows: list[Row] = []
    for utterance in CORPUS:
        synthesis = await tts.synthesise(
            SynthesisRequest(text=utterance.text, locale=utterance.locale)
        )
        pcm = synthesis.audio
        if pcm[:4] == b"RIFF":  # belt and braces — `raw` should not be wrapped
            pcm, _ = wav_to_pcm(pcm)

        transcription = await stt.transcribe(
            TranscriptionRequest(audio=pcm, sample_rate_hz=16_000, locale=utterance.locale)
        )
        rate, errors, words = wer(utterance.text, transcription.text)
        rows.append(
            Row(
                utterance=utterance,
                transcript=transcription.text,
                error_rate=rate,
                errors=errors,
                words=words,
                script=script_of(transcription.text),
                stt_language=stt_language_for(utterance.locale),
                detected=transcription.detected_language,
                audio_bytes=len(pcm),
            )
        )

        # The fixture the suite replays: the vendor's response SHAPE, and the
        # reference text beside it so a reader can see what produced it.
        (FIXTURES / f"stt_{utterance.name}.json").write_text(
            json.dumps(
                {
                    "$comment": (
                        "RECORDED from the live Cartesia API — do not hand-edit. "
                        "Re-record with `CARTESIA_API_KEY=... uv run python -m tests.voice.record`."
                    ),
                    "$reference": utterance.text,
                    "$why": utterance.why,
                    "locale": utterance.locale,
                    "stt_language_sent": stt_language_for(utterance.locale),
                    "response": {
                        "type": "transcript",
                        "is_final": True,
                        "language": transcription.detected_language,
                        "duration": (transcription.duration_ms or 0) / 1000,
                        "text": transcription.text,
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return rows


def report(rows: list[Row]) -> None:
    print()
    print("Cartesia round-trip — Sonic 3.5 → Ink (ink-whisper), 16 kHz mono s16le")
    print("SYNTHETIC: TTS audio, not human speech. A floor on the error rate, not an estimate.")
    print()
    header = f"{'locale':<9} {'lang sent':<10} {'WER':>8} {'errors':>8} {'script':<12} ok"
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row.utterance.locale:<9} {row.stt_language:<10} "
            f"{row.error_rate:>7.1%} {f'{row.errors}/{row.words}':>8} "
            f"{row.script:<12} {'yes' if row.script_ok else 'NO'}"
        )
    print()
    for row in rows:
        print(f"[{row.utterance.locale}] {row.utterance.why}")
        print(f"  ref : {row.utterance.text}")
        print(f"  got : {row.transcript}")
        print()


if __name__ == "__main__":
    rows = asyncio.run(record())
    report(rows)
