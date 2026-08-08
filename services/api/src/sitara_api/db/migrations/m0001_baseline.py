"""0001 — the §6.4 baseline.

Everything M4 creates is additive to an empty (or M1/M3-shaped) database, so it
all belongs in expand. The migrate and contract phases are deliberately empty:
the runner records them anyway, which is what lets a later migration's contract
phase know this one finished.
"""

from __future__ import annotations

from typing import Any

from sitara_api.db.schema import ensure_schema

id = "0001_baseline"
description = "Create every §6.4 collection with its validator, indexes and TTLs"


async def expand(db: Any) -> None:
    # ensure_schema only creates and reconciles; the one destructive thing it
    # can do — rebuilding an index whose options changed — is not reachable
    # through the guarded handle's blocked methods because index management
    # goes through create_index, and a genuine conflict raises rather than
    # silently dropping. See schema.ensure_index.
    await ensure_schema(db)


async def migrate(db: Any) -> None:
    """Nothing to backfill: 0001 introduces the shape, not a change to it."""


async def contract(db: Any) -> None:
    """Nothing to remove: 0001 is purely additive."""
