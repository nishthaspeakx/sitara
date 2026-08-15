"""0004 — §23's collections, and the message-class values that moved (M12).

Two things, and only the second one is interesting.

**The collections** — `push_subscriptions` (§23.6) and
`notification_preferences` (§23.5) — are additive and arrive with
`ensure_schema`. Nothing to backfill: a user with no preference row reads
`Preferences` defaults, which is the same document `store.load` would have
written, so backfilling one per user would be writing the answer we already
give.

**The message-class values are a RENAME**, and that is what needs a migrate
phase. `daily_guidance.notify` wrote §23.1's class as its LETTER — `"D"` — and
the set has moved to `sitara_schemas.notifications`, where the id is the word
and the letter is documentation (the same split §4.3's presence ordinals use,
and for the reason M8-P10 learned: a one-character wire value is a value two
sides can each interpret differently while both look right).

Rows already exist, so they are rewritten. The map is derived from
`MESSAGE_CLASS_LETTER` rather than typed out here, because a hand-copied
mapping of four single letters is exactly the kind of thing that is right today
and wrong after a fifth class — and this file would be the last place anyone
looked.

The phases earn their names again:

  **expand**   create the two collections and widen the validator. Old pods are
               still writing `"D"`, and both spellings must be accepted at
               once — which they are, because §6.4 types `message_class` as a
               string and never as an enum. That is not luck: an `enum:` clause
               there would make this migration undeployable without downtime.
  **migrate**  rewrite the letters. Idempotent — the second run matches nothing.
  **contract** nothing. No field is retired; only its values changed.

**Why the rewrite is safe to run while both spellings are live:** nothing reads
`message_class` to decide behaviour. §23.1's behaviour comes from
`classes.POLICIES`, keyed by the value the SENDER holds in memory, and the
stored field is a record of what was sent. A row mid-rewrite is therefore a row
whose analytics label is briefly stale, not a row that would be delivered
differently.
"""

from __future__ import annotations

import logging
from typing import Any

from sitara_schemas.notifications import MESSAGE_CLASS_LETTER

from sitara_api.db.schema import ensure_schema

logger = logging.getLogger(__name__)

id = "0004_notification_vocabulary"
description = (
    "Add push_subscriptions + notification_preferences (§23.5/§23.6) and "
    "rewrite notifications.message_class from §23.1's letters to the schema ids"
)

#: letter → id, derived. See the module header for why it is not typed out.
_LETTER_TO_ID: dict[str, str] = {
    letter: message_class.value
    for message_class, letter in MESSAGE_CLASS_LETTER.items()
}


async def expand(db: Any) -> None:
    await ensure_schema(db)


async def migrate(db: Any) -> None:
    """Rewrite the letters. `$in` on the letters matches nothing on a re-run."""
    rewritten = 0
    for letter, message_class in _LETTER_TO_ID.items():
        result = await db.notifications.update_many(
            {"message_class": letter},
            {"$set": {"message_class": message_class}},
        )
        rewritten += result.modified_count
    logger.info("rewrote message_class on %d notifications", rewritten)


async def contract(db: Any) -> None:
    """Nothing to remove: 0004 renames values and adds collections."""
