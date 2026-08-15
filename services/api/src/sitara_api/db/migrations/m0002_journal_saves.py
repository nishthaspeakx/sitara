"""0002 — `journal_saves` (CC-011 §44).

§30.5 names five Journal artefact types and §6.4 had homes for four; saved
guidance had none, which is why `MessageActions`' "save to journal" has been
wired to nothing since M8. CC-011 added the collection to the table, so this
migration is `ensure_schema` again: the registry is the declaration and the
creator reads it, so there is nothing collection-specific to write here.

Additive, like 0001 — a collection that did not exist cannot have data to
backfill and nothing is removed.
"""

from __future__ import annotations

from typing import Any

from sitara_api.db.schema import ensure_schema

id = "0002_journal_saves"
description = "Create journal_saves with its validator and indexes (CC-011 §44)"


async def expand(db: Any) -> None:
    await ensure_schema(db)


async def migrate(db: Any) -> None:
    """Nothing to backfill: there were no saves to move, because there was
    nowhere to put one."""


async def contract(db: Any) -> None:
    """Nothing to remove: 0002 is purely additive."""
