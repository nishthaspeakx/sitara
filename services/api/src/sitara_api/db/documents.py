"""Document stamping — the §6.4 preamble, applied.

"every doc carries `_id`, `created_at`, `updated_at`, `schema_v`" is a rule the
validators now enforce, so writers need one obvious way to satisfy it rather
than three hand-rolled ones.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

#: Bumped by a migration, never by hand at a call site.
CURRENT_SCHEMA_V = 1


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def stamp(
    document: dict[str, Any], *, schema_v: int = CURRENT_SCHEMA_V, now: dt.datetime | None = None
) -> dict[str, Any]:
    """Add the four fields §6.4 requires of every document, in place.

    `created_at` is preserved when the caller already set one — replacing a
    cache row must not reset the age of the thing it replaces.
    """
    moment = now or utcnow()
    document.setdefault("created_at", moment)
    document["updated_at"] = moment
    document.setdefault("schema_v", schema_v)
    return document
