"""expand → migrate → contract migration runner (§14-deploy).

The three phases exist so a schema change never requires the code and the
database to change in the same instant:

  **expand**    add what the new code needs, additively. Old code still runs.
  **migrate**   backfill and dual-write. Both versions of the code still run.
  **contract**  remove what only the old code needed. Old code is gone by now.

Two rules are enforced rather than documented:

1. **expand cannot destroy.** The phase runs against a guarded database handle
   that raises on drops, deletes and `$unset`. A migration that needs to remove
   something has a contract phase; if it tries to do it in expand, the deploy
   fails at the migration rather than at 3am when the old pods are still up.

2. **contract cannot outrun migrate.** A contract phase refuses to run until
   that migration's migrate phase is recorded complete, so nothing is dropped
   before the data that depended on it has moved.

A single-document advisory lock keeps two pods from racing the same phase.
"""

from __future__ import annotations

import datetime as dt
import os
import socket
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from pymongo.errors import DuplicateKeyError

from sitara_api.db.connection import MongoDb

LEDGER = "schema_migrations"
LOCK_ID = "lock"
LOCK_STALE_AFTER = dt.timedelta(minutes=30)

PHASES: tuple[str, ...] = ("expand", "migrate", "contract")


class MigrationError(RuntimeError):
    pass


class DestructiveExpandError(MigrationError):
    """An expand phase tried to remove something. Expand is additive-only."""


class ContractTooEarlyError(MigrationError):
    """A contract phase ran before its own migrate phase was recorded."""


class Migration(Protocol):
    id: str
    description: str

    async def expand(self, db: Any) -> None: ...
    async def migrate(self, db: Any) -> None: ...
    async def contract(self, db: Any) -> None: ...


# ---------------------------------------------------------------------------
# The expand guard


# Index management is deliberately absent from this set. An index holds no data
# — it is derived from the documents — so rebuilding one whose options changed
# loses nothing, and blocking it would leave expand unable to correct an index
# without a full migration. Everything that can lose a document is blocked.
_DESTRUCTIVE_COLLECTION_METHODS = frozenset(
    {
        "drop",
        "delete_one",
        "delete_many",
        "find_one_and_delete",
        "rename",
    }
)
_DESTRUCTIVE_UPDATE_OPERATORS = frozenset({"$unset", "$pop", "$pull", "$pullAll"})


class _GuardedCollection:
    def __init__(self, collection: Any, name: str) -> None:
        self._collection = collection
        self._name = name

    def __getattr__(self, item: str) -> Any:
        if item in _DESTRUCTIVE_COLLECTION_METHODS:
            raise DestructiveExpandError(
                f"expand phase called {self._name}.{item}() — expand is additive-only; "
                "move the removal to the contract phase"
            )
        target = getattr(self._collection, item)
        if item in ("update_one", "update_many", "find_one_and_update", "bulk_write"):
            return _guard_update(target, self._name, item)
        return target


def _guard_update(target: Callable[..., Awaitable[Any]], name: str, method: str):
    async def guarded(*args: Any, **kwargs: Any) -> Any:
        for arg in args:
            _reject_destructive_update(arg, name, method)
        return await target(*args, **kwargs)

    return guarded


def _reject_destructive_update(arg: Any, name: str, method: str) -> None:
    if isinstance(arg, dict):
        used = _DESTRUCTIVE_UPDATE_OPERATORS & set(arg)
        if used:
            raise DestructiveExpandError(
                f"expand phase used {sorted(used)} in {name}.{method}() — expand is "
                "additive-only; move the removal to the contract phase"
            )
    elif isinstance(arg, (list, tuple)):
        for item in arg:
            _reject_destructive_update(item, name, method)


class GuardedDb:
    """A database handle that refuses to destroy anything."""

    def __init__(self, db: MongoDb) -> None:
        self._db = db

    def __getattr__(self, item: str) -> Any:
        if item in ("drop_collection", "drop"):
            raise DestructiveExpandError(
                f"expand phase called db.{item}() — expand is additive-only"
            )
        attr = getattr(self._db, item)
        return _GuardedCollection(attr, item) if _looks_like_collection(attr) else attr

    def __getitem__(self, name: str) -> Any:
        return _GuardedCollection(self._db[name], name)


def _looks_like_collection(value: Any) -> bool:
    return hasattr(value, "insert_one") and hasattr(value, "create_index")


# ---------------------------------------------------------------------------
# The runner


@dataclass
class MigrationReport:
    phase: str
    applied: list[str]
    skipped: list[str]

    def summary(self) -> str:
        return (
            f"{self.phase}: {len(self.applied)} applied"
            f"{', ' + str(len(self.skipped)) + ' already recorded' if self.skipped else ''}"
        )


def _holder() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


async def acquire_lock(db: MongoDb, *, stale_after: dt.timedelta = LOCK_STALE_AFTER) -> bool:
    now = _now()
    try:
        await db[LEDGER].insert_one(
            {
                "_id": LOCK_ID,
                "holder": _holder(),
                "acquired_at": now,
                "created_at": now,
                "updated_at": now,
                "schema_v": 1,
            }
        )
        return True
    except DuplicateKeyError:
        pass

    # A crashed run must not wedge every future deploy — but only a genuinely
    # stale lock is broken, and breaking one is recorded in the row itself.
    existing = await db[LEDGER].find_one({"_id": LOCK_ID})
    if existing is None:
        return False  # released between the insert and the read — let the caller retry
    acquired_at = existing.get("acquired_at")
    if acquired_at is None:
        return False
    if acquired_at.tzinfo is None:
        acquired_at = acquired_at.replace(tzinfo=dt.UTC)
    if now - acquired_at < stale_after:
        return False
    result = await db[LEDGER].update_one(
        {"_id": LOCK_ID, "acquired_at": existing["acquired_at"]},
        {"$set": {"holder": _holder(), "acquired_at": now, "updated_at": now}},
    )
    return result.modified_count == 1


async def release_lock(db: MongoDb) -> None:
    await db[LEDGER].delete_one({"_id": LOCK_ID})


async def is_recorded(db: MongoDb, migration_id: str, phase: str) -> bool:
    return await db[LEDGER].find_one({"_id": f"{migration_id}:{phase}"}) is not None


async def record(db: MongoDb, migration_id: str, phase: str) -> None:
    now = _now()
    await db[LEDGER].update_one(
        {"_id": f"{migration_id}:{phase}"},
        {
            "$set": {
                "migration_id": migration_id,
                "phase": phase,
                "applied_at": now,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now, "schema_v": 1},
        },
        upsert=True,
    )


async def run_phase(
    db: MongoDb,
    migrations: Sequence[Migration],
    phase: str,
    *,
    lock: bool = True,
) -> MigrationReport:
    if phase not in PHASES:
        raise MigrationError(f"unknown phase {phase!r}; expected one of {PHASES}")

    if lock and not await acquire_lock(db):
        raise MigrationError("another migration run holds the lock")

    report = MigrationReport(phase=phase, applied=[], skipped=[])
    try:
        for migration in migrations:
            if await is_recorded(db, migration.id, phase):
                report.skipped.append(migration.id)
                continue
            if phase == "contract" and not await is_recorded(db, migration.id, "migrate"):
                raise ContractTooEarlyError(
                    f"{migration.id}: contract cannot run before its migrate phase is "
                    "recorded — the data it drops may not have moved yet"
                )
            handle = GuardedDb(db) if phase == "expand" else db
            await getattr(migration, phase)(handle)
            await record(db, migration.id, phase)
            report.applied.append(migration.id)
    finally:
        if lock:
            await release_lock(db)
    return report
