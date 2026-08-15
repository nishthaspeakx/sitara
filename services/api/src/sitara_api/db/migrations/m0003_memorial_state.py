"""0003 — `family_members.memorial_state` (CC-012 §45).

Unlike 0001 and 0002 this one has a real MIGRATE phase: the field is not
nullable, so every family member that already exists needs the default before
any code may rely on reading it.

The three phases earn their separation here for the first time:

  **expand**  — widen the validator so `memorial_state` is permitted. Old code
                is still running and still writing rows without it; a validator
                that REQUIRED the field in this phase would reject every write
                from the pods that have not been replaced yet.
  **migrate** — backfill `living` onto every existing member. Both versions of
                the code run happily: the old ignores the field, the new reads
                a value that is now always there.
  **contract** — nothing. The field is additive and no old field is retired.

`living` is the right backfill and not merely the safe one: §45 makes it the
default, and every member recorded before this migration was recorded by a
user who had not been offered the alternative.
"""

from __future__ import annotations

import logging
from typing import Any

from sitara_api.db.schema import ensure_schema

logger = logging.getLogger(__name__)

id = "0003_memorial_state"
description = "Add family_members.memorial_state and backfill `living` (CC-012 §45)"

#: §45's default. Imported by the family module rather than re-spelled there.
LIVING = "living"


async def expand(db: Any) -> None:
    await ensure_schema(db)


async def migrate(db: Any) -> None:
    """Backfill. Idempotent — `$exists: false` matches nothing on a re-run,
    which is what `task_acks_late` and a retried deploy both need."""
    result = await db.family_members.update_many(
        {"memorial_state": {"$exists": False}},
        {"$set": {"memorial_state": LIVING}},
    )
    logger.info("backfilled memorial_state on %d family members", result.modified_count)


async def contract(db: Any) -> None:
    """Nothing to remove: 0003 is additive."""
