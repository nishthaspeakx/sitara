"""§3.4's pronunciation-override system, applied to the TTS adapter.

§3.4: "per-language dictionary (grapheme→phoneme or vendor-native lexicon
format) stored in `pronunciation_dictionaries` (§6.4), editable in admin with
audio preview, versioned, hot-reloaded into the TTS adapter". This is the
grapheme→phoneme half — a respelling the engine says correctly — because a
vendor-hosted lexicon is a resource created through the vendor's API, and a
dictionary that only exists inside a vendor account is not the reviewable,
versioned thing §3.4 asks for.

The one rule that makes this safe
---------------------------------

**A respelling reaches the synthesiser and NOTHING else.** The stored message,
the transcript §25.4's toggle shows, the guidance log, the memory chip — all
carry the real words. If a respelling ever leaked into a transcript, the user
would read "raahoo kaal" in their own thread, and §30.4's Trust Sheet would
cite a fact against a sentence nobody wrote.

That is not a convention here. `apply` is called in exactly one place —
`VoiceNoteService._synthesise_reply`, on the way into `SynthesisRequest` — and
`tests/voice/test_pronunciation.py` asserts the stored turn text is untouched.

Why the entries are all `draft`
-------------------------------

§3.4 gives this corpus an owner (the localisation lead) and a reviewer (the
Jyotish lead, plus §14's native panel), and neither has seen these. `status`
stays `draft` and `applied()` is deliberately willing to serve draft rows in
dev — a dictionary nobody can hear is a dictionary nobody can review — while
`REQUIRE_REVIEWED` makes production serve only approved ones.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from sitara_api import text as textutil

logger = logging.getLogger(__name__)

POLICY_PATH = Path(__file__).parent / "policy" / "pronunciation.json"

#: §3.4 wants every override reviewed. Until the §14 panel has run, dev and
#: test serve drafts so they can be HEARD; anything else serves approved only.
REQUIRE_REVIEWED = frozenset({"prod", "staging", "beta"})

APPROVED = "approved"


@dataclass(frozen=True)
class Override:
    term: str
    phonetic: str
    status: str
    reviewed_by: str | None = None
    note: str | None = None

    @property
    def reviewed(self) -> bool:
        return self.status == APPROVED and bool(self.reviewed_by)


@lru_cache(maxsize=1)
def _policy() -> dict[str, Any]:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=8)
def overrides_for(locale: str) -> tuple[Override, ...]:
    """Every declared override for a locale, reviewed or not."""
    block = _policy()["locales"].get(locale)
    if block is None:
        return ()
    return tuple(
        Override(
            term=row["term"],
            phonetic=row["phonetic"],
            status=row["status"],
            reviewed_by=row.get("reviewed_by"),
            note=row.get("note"),
        )
        for row in block["terms"]
        if not row.get("$comment")
    )


@lru_cache(maxsize=16)
def _matcher(locale: str, reviewed_only: bool) -> tuple[re.Pattern[str] | None, dict[str, str]]:
    """One alternation over every term, longest-first.

    Longest-first matters: "rahu kaal" and "rahukaal" are both entries, and so
    are "abhijit muhurat" and (in a fuller corpus) "muhurat". A shortest-first
    alternation would rewrite the inner term and leave the outer one half
    respelled.

    `textutil.alternation` rather than `\\b`: §CL-003 — Devanagari vowel signs
    and the virama are combining marks Python excludes from `\\w`, so a word
    boundary around `राहु काल` matches nothing at all.
    """
    rows = [o for o in overrides_for(locale) if o.reviewed or not reviewed_only]
    if not rows:
        return None, {}
    by_surface = {o.term.lower(): o.phonetic for o in rows}
    ordered = sorted(by_surface, key=len, reverse=True)
    return textutil.alternation(ordered, min_length=2), by_surface


def apply(text: str, locale: str, *, environment: str = "dev") -> str:
    """Respell `text` for the synthesiser. Never for storage, never for display.

    Returns the input unchanged when the locale has no dictionary, which is the
    honest behaviour for the five §3.3 languages M9 does not yet serve: a term
    said plainly is worse than one said well and far better than one said in a
    language it does not belong to.
    """
    pattern, surfaces = _matcher(locale, environment in REQUIRE_REVIEWED)
    if pattern is None:
        return text

    def swap(match: re.Match[str]) -> str:
        return surfaces.get(match.group(0).lower(), match.group(0))

    return pattern.sub(swap, text)


def review_status() -> dict[str, Any]:
    """What `/shipcheck` and §12's admin surface report.

    Counts rather than a boolean, because "the dictionary is unreviewed" and
    "the dictionary is 90% reviewed" are different states and only one of them
    is close to shippable.
    """
    total = reviewed = 0
    per_locale: dict[str, dict[str, int]] = {}
    for locale in _policy()["locales"]:
        rows = overrides_for(locale)
        ok = sum(1 for o in rows if o.reviewed)
        per_locale[locale] = {"total": len(rows), "reviewed": ok}
        total += len(rows)
        reviewed += ok
    return {
        "total": total,
        "reviewed": reviewed,
        "per_locale": per_locale,
        "spec": "§3.4 — native panel MOS ≥4.2 and zero critical mispronunciations to ship",
    }


def seed_documents(now: Any = None) -> list[dict[str, Any]]:
    """Rows for §6.4's `pronunciation_dictionaries`, for the admin surface.

    The JSON file is the source of truth and the collection is the editable
    copy §3.4 asks for — same direction as `packages/i18n` → `localized_content`.
    A reviewer edits in admin; a change here is a code review.
    """
    from sitara_api.db.documents import stamp

    documents: list[dict[str, Any]] = []
    for locale in _policy()["locales"]:
        for override in overrides_for(locale):
            documents.append(
                stamp(
                    {
                        "locale": locale,
                        "term": override.term,
                        "phonetic": override.phonetic,
                        "audio_preview_ref": None,
                        "status": override.status,
                        # §3.4: "Every override records author + review status."
                        # A cited extension to §6.4's cell — the table names the
                        # status and not who granted it, and a review nobody
                        # signed is not a review.
                        "reviewed_by": override.reviewed_by,
                    },
                    now=now,
                )
            )
    return documents
