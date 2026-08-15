"""Render the same lines in all three locales so Tara can be judged BY EAR.

    uv run python -m scripts.compare_voices
    uv run python -m scripts.compare_voices --out ~/Desktop/tara --no-dictionary

§3.2's architecture is "one personality, anchor clone for EN/Hinglish/HI". This
repo has TWO Cartesia voices covering three locales (`providers/voices.py`), and
whether they read as the same woman is not something a test can answer. It is a
§3.2 acceptance-gate question — "emotional-consistency panel ≥4.2" — and this
script exists to put the audio in front of a person.

What it writes, into `--out` (default `voice-compare/` at the repo root):

    01-greeting.en.wav        the SAME sentence, three ways — the one that
    01-greeting.hi.wav        answers "is this one woman or three?"
    01-greeting.hi-Latn.wav
    02-codemix.hi-Latn.wav    genuinely code-mixed Hinglish, the hardest case
    03-tradition.*.wav        rahu kaal · muhurat · nakshatra, per locale
    04-numerals.*.wav         CC-013: Latin digits, dates and clock times
    05-brief.*.wav            a real morning-brief sentence, in register
    MANIFEST.txt              what was said, in what voice, how long it ran

Every line goes through §3.4's dictionary on the way in, exactly as the product
does — `--no-dictionary` renders the same lines WITHOUT it, so the two can be
compared and the dictionary's value heard rather than assumed.

Nothing here is a fixture and nothing is committed: it calls the live vendor and
writes audio for a human to play. It costs real Cartesia credit.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import sys
from pathlib import Path

from sitara_api.voice.audio import pcm_to_wav
from sitara_api.voice.config import VoiceSettings
from sitara_api.voice.pronunciation import apply as apply_dictionary
from sitara_api.voice.providers.base import SynthesisRequest, VoiceProviderUnavailable
from sitara_api.voice.providers.voices import TARA_VOICES, voiced_locales

LOCALES = voiced_locales()

#: (slug, {locale: line}). Written as parallel text rather than translated here
#: — §2.4 keeps copy in the catalogs, and these are QA lines, not product copy.
LINES: tuple[tuple[str, str, dict[str, str]], ...] = (
    (
        "01-greeting",
        "THE COMPARISON LINE — same sentence, three voices. One woman or three?",
        {
            "en": "Namaste. I'm Tara. I'll be here with you each morning, "
            "and there's no hurry about any of it.",
            "hi": "नमस्ते। मैं तारा हूँ। हर सुबह मैं आपके साथ रहूँगी, "
            "और किसी बात की जल्दी नहीं है।",
            "hi-Latn": "Namaste. Main Tara hoon. Har subah main aapke saath rahungi, "
            "aur kisi baat ki jaldi nahin hai.",
        },
    ),
    (
        "02-codemix",
        "THE HARD CASE — real Hinglish: English nouns inside Hindi structure. "
        "Rendered in all three so the Hindi-voice choice for hi-Latn can be heard "
        "against the English voice reading the same words.",
        {
            "hi-Latn": "Aapki team meeting ke liye 11 baje ka slot theek rahega, "
            "lekin agar aap presentation ko thoda postpone kar sakein toh "
            "afternoon ka window zyada favourable hai.",
            "en": "Aapki team meeting ke liye 11 baje ka slot theek rahega, "
            "lekin agar aap presentation ko thoda postpone kar sakein toh "
            "afternoon ka window zyada favourable hai.",
            "hi": "आपकी टीम मीटिंग के लिए 11 बजे का स्लॉट ठीक रहेगा, "
            "लेकिन अगर आप प्रेज़ेंटेशन को थोड़ा पोस्टपोन कर सकें तो "
            "दोपहर का विंडो ज़्यादा अनुकूल है।",
        },
    ),
    (
        "03-tradition",
        "§3.4's own vocabulary — rahu kaal, muhurat, nakshatra. This is what the "
        "dictionary exists for; compare against --no-dictionary.",
        {
            "en": "Rahu kaal runs from 9:33 to 11:16 this morning, so the abhijit "
            "muhurat just after noon is the better window. The Moon is in the "
            "nakshatra Uttara Phalguni today.",
            "hi": "आज सुबह राहु काल 9:33 से 11:16 तक है, इसलिए दोपहर के ठीक बाद "
            "का अभिजित मुहूर्त बेहतर समय है। चंद्रमा आज उत्तरा फाल्गुनी "
            "नक्षत्र में हैं।",
            "hi-Latn": "Aaj subah rahu kaal 9:33 se 11:16 tak hai, isliye dopahar ke "
            "theek baad ka abhijit muhurat behtar samay hai. Chandra aaj "
            "Uttara Phalguni nakshatra mein hain.",
        },
    ),
    (
        "04-numerals",
        "CC-013 — Latin digits in EVERY locale. Listen for dates and clock times "
        "read as a person says them, not digit by digit.",
        {
            "en": "On 15 August 2026, the window runs from 12:32 to 13:27, and "
            "your renewal is on 3 March at 6:45 in the morning.",
            "hi": "15 अगस्त 2026 को यह समय 12:32 से 13:27 तक रहेगा, और आपका "
            "नवीनीकरण 3 मार्च को सुबह 6:45 पर है।",
            "hi-Latn": "15 August 2026 ko yeh samay 12:32 se 13:27 tak rahega, aur "
            "aapka renewal 3 March ko subah 6:45 par hai.",
        },
    ),
    (
        "05-brief",
        "A real morning-brief sentence, in §7.1's register — unhurried, no urgency.",
        {
            "en": "Today runs on Shukla paksha, tithi 3. There's a good window "
            "between 12:32 and 13:27 — nothing that needs rushing.",
            "hi": "आज शुक्ल पक्ष है, तिथि 3 है। 12:32 से 13:27 तक समय शुभ है — "
            "जल्दबाज़ी की कोई ज़रूरत नहीं।",
            "hi-Latn": "Aaj Shukla paksha hai, tithi 3 chal rahi hai. 12:32 se 13:27 "
            "tak ka samay achha rahega — jaldbaazi ki koi zarurat nahin.",
        },
    ),
)


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scripts.compare_voices")
    parser.add_argument("--out", default="voice-compare", help="output directory")
    parser.add_argument(
        "--no-dictionary",
        action="store_true",
        help="skip §3.4's respellings, to hear what they are worth",
    )
    parser.add_argument("--locale", action="append", default=[], help="limit locales")
    args = parser.parse_args(argv)

    settings = VoiceSettings()
    if not settings.cartesia_api_key:
        print("CARTESIA_API_KEY is not set — nothing to render.", file=sys.stderr)
        return 1

    from sitara_api.voice.providers.cartesia import CartesiaTtsProvider

    tts = CartesiaTtsProvider(settings.cartesia_api_key, model=settings.tts_model)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    wanted = tuple(args.locale) or LOCALES

    manifest: list[str] = [
        "Tara — voice comparison",
        f"rendered  {dt.datetime.now().isoformat(timespec='seconds')}",
        f"model     {settings.tts_model}",
        f"dictionary {'OFF (--no-dictionary)' if args.no_dictionary else 'ON (§3.4)'}",
        "",
        "voices (providers/voices.py):",
        *(f"  {loc:8s} {TARA_VOICES[loc]}" for loc in LOCALES),
        "",
        "NOTE: hi-Latn deliberately uses the HINDI voice — Hinglish is spoken",
        "Hindi with English words in it, so Hindi prosody is the right base.",
        "02-codemix renders the same Hinglish sentence in all three so that",
        "choice can be heard rather than argued.",
        "",
    ]

    written = failed = 0
    for slug, note, per_locale in LINES:
        manifest += [f"── {slug} ──", note, ""]
        for locale in wanted:
            text = per_locale.get(locale)
            if text is None:
                continue
            spoken = (
                text
                if args.no_dictionary
                else apply_dictionary(text, locale, environment="dev")
            )
            try:
                result = await tts.synthesise(
                    SynthesisRequest(text=spoken, locale=locale)
                )
            except VoiceProviderUnavailable as exc:
                print(f"  {slug}.{locale}: {exc}", file=sys.stderr)
                manifest.append(f"  {locale:8s} FAILED — {exc}")
                failed += 1
                continue

            path = out / f"{slug}.{locale}.wav"
            path.write_bytes(pcm_to_wav(result.audio, result.sample_rate_hz))
            seconds = len(result.audio) / 2 / result.sample_rate_hz
            written += 1
            print(f"  {path.name:28s} {seconds:5.2f}s  voice={result.voice_id}")
            manifest.append(f"  {locale:8s} {seconds:5.2f}s  {path.name}")
            manifest.append(f"           said: {text}")
            if spoken != text:
                # §3.4 reaches the synthesiser and nothing else — this line is
                # the only place the respelling is ever legible, and it is a QA
                # artefact rather than anything a user sees.
                manifest.append(f"           sent: {spoken}")
        manifest.append("")

    (out / "MANIFEST.txt").write_text("\n".join(manifest), encoding="utf-8")
    print(f"\n{written} file(s) in {out.resolve()}  ({failed} failed)")
    print("Play 01-greeting.* back to back first — that is the one-woman question.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
