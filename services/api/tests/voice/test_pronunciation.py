"""§3.4's pronunciation overrides, and the one way they could do harm.

A respelling exists so an engine says a word correctly. It is not a spelling
correction, not a normalisation, and not something a user should ever read. The
tests that matter here are therefore mostly about where it does NOT reach.
"""

from __future__ import annotations

import pytest

from sitara_api.voice import pronunciation
from tests.chat.conftest import build_env
from tests.voice.conftest import RecordingTts
from tests.voice.test_grounding_parity import build_voice, speak

# A CLAIMLESS sentence that still carries the term.
#
# The obvious draft — "Your rahu kaal today runs from 3:00 PM to 4:30 PM" —
# is rejected by grounding, correctly: the served payload holds a transit-house
# fact and nothing with a clock in it, so those times stand on nothing. It
# burned the §9 regeneration and the turn fell back to the safe line, which
# carries no astrology term at all and so tested nothing.
#
# §9's exemption is the right instrument: a category term GLOSSED as a concept
# may go uncited when there is no number, no clock value, no second person, no
# temporal deixis and no celestial assertion (§2.3 requires that gloss).
CLAIMLESS_WITH_TERM = "Rahu kaal is a window the tradition treats as inauspicious."
CLAIMLESS_HI = "राहु काल एक ऐसा समय है जिसे परंपरा शुभ नहीं मानती।"


# --------------------------------------------------------------------------
# The dictionary itself


def test_the_joined_and_spaced_spellings_say_the_same_thing() -> None:
    """M9's live run found Ink writing spoken "rahu kaal" as "Rahukaal". Both
    spellings therefore reach the synthesiser in real traffic, and a dictionary
    that only knew one would fix half the cases."""
    for locale in ("en", "hi-Latn"):
        spaced = pronunciation.apply("rahu kaal today", locale)
        joined = pronunciation.apply("rahukaal today", locale)
        assert spaced == joined, locale
        assert "raah" in spaced


def test_devanagari_terms_are_matched_at_all() -> None:
    """CL-003: `\\b` around `राहु काल` matches nothing, because the vowel signs
    and the virama are combining marks Python excludes from `\\w`. The shared
    `textutil.alternation` is what makes this work, and a test that only
    covered Latin would never have noticed."""
    out = pronunciation.apply("आज राहु काल कब है?", "hi")
    assert out != "आज राहु काल कब है?"
    assert "राहु" in out


def test_the_longest_term_wins() -> None:
    """"rahu kaal" and "rahukaal" are both entries. A shortest-first
    alternation would rewrite an inner term and leave the outer one half
    respelled — audible as a stutter rather than a mispronunciation."""
    out = pronunciation.apply("abhijit muhurat", "en")
    assert out == "abhijit  muhoorat"


def test_an_unmapped_locale_is_returned_untouched() -> None:
    """§3.3 has eight launch languages and M9 dictionaries three. A term said
    plainly is worse than one said well, and far better than one said in a
    language it does not belong to."""
    assert pronunciation.apply("rahu kaal", "ta") == "rahu kaal"


def test_production_serves_only_reviewed_overrides() -> None:
    """§3.4 gives this corpus a reviewer, and nobody has reviewed it. Drafts are
    audible in dev so they CAN be reviewed; production hears none of them."""
    assert pronunciation.apply("rahu kaal", "en", environment="dev") != "rahu kaal"
    assert pronunciation.apply("rahu kaal", "en", environment="prod") == "rahu kaal"

    status = pronunciation.review_status()
    assert status["total"] > 0
    assert status["reviewed"] == 0, (
        "if this ever passes with a non-zero count, someone signed off — check "
        "that it was the §14 native panel and not a default"
    )


def test_every_row_carries_a_status_and_a_reviewer_slot() -> None:
    """§3.4: "Every override records author + review status." A row with no
    slot for who approved it is a row that can never be honestly approved."""
    for locale in ("en", "hi", "hi-Latn"):
        rows = pronunciation.overrides_for(locale)
        assert rows, locale
        for row in rows:
            assert row.status
            assert not row.reviewed  # nothing is signed off yet
    documents = pronunciation.seed_documents()
    assert documents and all("reviewed_by" in d for d in documents)


# --------------------------------------------------------------------------
# Where a respelling must never reach


@pytest.mark.asyncio
async def test_the_respelling_reaches_the_synthesiser_and_nothing_else() -> None:
    """The whole risk, in one test.

    If a respelling leaked into the stored turn, the user would read
    "raahoo kaal" in their own thread, §25.4's transcript toggle would disagree
    with itself, and §30.4's Trust Sheet would cite a fact against a sentence
    nobody wrote.
    """
    env = build_env()
    env.llm.script("generate", CLAIMLESS_WITH_TERM)
    tts = RecordingTts()

    result = await speak(env, build_voice(env, transcript="what is rahu kaal?", tts=tts))

    # The synthesiser heard the respelling...
    assert tts.texts and "raahoo  kaal" in tts.texts[0]
    # ...and everything the user can see kept the real words. Case-insensitive:
    # the match is case-insensitive by design (a sentence-initial "Rahu kaal"
    # must be respelled too), so the turn keeps its own capitalisation.
    assert "rahu kaal" in result.turn.text.lower()
    assert "raahoo" not in result.turn.text.lower()
    stored = env.store.messages[-1]
    assert "raahoo" not in str(stored.get("content", ""))


@pytest.mark.asyncio
async def test_a_locale_with_no_dictionary_still_speaks() -> None:
    """`apply` returning the input unchanged must not become a decline. The
    five §3.3 languages without a dictionary still get a voice."""
    env = build_env()
    env.llm.script("generate", CLAIMLESS_HI)
    tts = RecordingTts()

    result = await speak(
        env, build_voice(env, transcript="राहु काल क्या है?", tts=tts), locale="hi"
    )

    assert tts.texts
    assert result.tts_audio_asset_id is not None
