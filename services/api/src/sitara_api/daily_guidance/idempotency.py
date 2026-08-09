"""§32.13's idempotency key, and the one subtlety in it.

    "`daily_briefings` adopts the night-reflection rule: one brief per
    user-local calendar date, bound at generation time; idempotency key =
    user + local-date + locale. Date-line crossings can neither double-fire
    nor skip (a missed local date generates on open)."

The key carries THREE components; the unique index carries two. That is not a
contradiction, it is the mechanism §32.7 needs:

    "Locale change joins location change as a targeted-regenerate trigger
    (§7.1): an undelivered brief in the old locale is discarded (idempotency
    key includes locale) and regenerated."

If locale were part of the uniqueness constraint, a user who switched from
Hindi to Hinglish at 06:50 would end the morning holding TWO briefs for one
local date — and §32.13's "one brief per user-local calendar date" would be
false. So `(user_id, date)` stays unique and the locale rides inside the stored
key: a generator comparing its computed key against the stored one learns that
the row it found is for the wrong language, and §32.7's rule — discard and
regenerate, never deliver the wrong language (§2.4) — has something to act on.

The alternative, comparing the stored `locale` column directly, would work
today and would quietly stop working the moment a fourth component joins the
key. Comparing keys compares whatever the key is made of.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo


def briefing_key(user_id: str, local_date: str, locale: str) -> str:
    """§32.13's key. Order is the spec's: user, local-date, locale."""
    return f"brief:{user_id}:{local_date}:{locale}"


def local_date_for(moment: dt.datetime, timezone: str) -> str:
    """The user's LOCAL calendar date at an instant (§32.13).

    Never `moment.date()`. A UTC date is a different date from the user's for
    part of every day — five and a half hours of it in India, and the whole of
    it for anyone who crossed the date line overnight, which is the case §32.13
    names explicitly.
    """
    return moment.astimezone(ZoneInfo(timezone)).date().isoformat()


def is_stale(stored_key: str, expected_key: str) -> bool:
    """True when the stored brief was bound under a different key (§32.7).

    Callers use this to decide "regenerate" rather than "deliver". An empty
    stored key counts as stale: a row written before the key existed cannot be
    shown to match, and regenerating one brief is cheaper than delivering one
    in a language the user has stopped reading.
    """
    return stored_key != expected_key
