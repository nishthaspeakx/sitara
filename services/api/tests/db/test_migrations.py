"""The expand→migrate→contract runner (§14-deploy)."""

from __future__ import annotations

import datetime as dt

import pytest

from sitara_api.db.migrations import ALL, run_phase
from sitara_api.db.migrations.runner import (
    LEDGER,
    LOCK_ID,
    ContractTooEarlyError,
    DestructiveExpandError,
    MigrationError,
    acquire_lock,
    is_recorded,
    release_lock,
)

pytestmark = pytest.mark.asyncio


class _Recorder:
    """A migration whose phases just note that they ran."""

    def __init__(self, migration_id: str = "9001_test") -> None:
        self.id = migration_id
        self.description = "test"
        self.ran: list[str] = []

    async def expand(self, db) -> None:  # noqa: ANN001
        self.ran.append("expand")

    async def migrate(self, db) -> None:  # noqa: ANN001
        self.ran.append("migrate")

    async def contract(self, db) -> None:  # noqa: ANN001
        self.ran.append("contract")


class _DroppingExpand(_Recorder):
    async def expand(self, db) -> None:  # noqa: ANN001
        await db.users.drop()


class _UnsettingExpand(_Recorder):
    async def expand(self, db) -> None:  # noqa: ANN001
        await db.users.update_many({}, {"$unset": {"locale": ""}})


class _DeletingExpand(_Recorder):
    async def expand(self, db) -> None:  # noqa: ANN001
        await db.users.delete_many({})


#: Derived from `ALL` rather than transcribed, so adding a migration does not
#: mean editing this file. The runner's contract is "every declared migration,
#: in declaration order" — pinning the list here would make these tests assert
#: which migrations exist, which is `migrations/__init__.py`'s job.
ALL_IDS = [m.id for m in ALL]


class TestBaseline:
    async def test_expand_builds_the_whole_registry(self, raw_db) -> None:
        report = await run_phase(raw_db, ALL, "expand")
        assert report.applied == ALL_IDS
        assert "users" in await raw_db.list_collection_names()
        # CC-011's collection is part of "the whole registry" now.
        assert "journal_saves" in await raw_db.list_collection_names()

    async def test_rerunning_expand_is_a_no_op(self, raw_db) -> None:
        await run_phase(raw_db, ALL, "expand")
        report = await run_phase(raw_db, ALL, "expand")
        assert report.applied == []
        assert report.skipped == ALL_IDS

    async def test_the_full_sequence_records_all_three_phases(self, raw_db) -> None:
        for phase in ("expand", "migrate", "contract"):
            await run_phase(raw_db, ALL, phase)
        for migration_id in ALL_IDS:
            for phase in ("expand", "migrate", "contract"):
                assert await is_recorded(raw_db, migration_id, phase)


class TestExpandIsAdditiveOnly:
    """A deploy that drops in expand takes down the old pods that are still up."""

    @pytest.mark.parametrize(
        "migration_class", [_DroppingExpand, _UnsettingExpand, _DeletingExpand]
    )
    async def test_a_destructive_expand_is_refused(self, db, migration_class) -> None:  # noqa: ANN001
        migration = migration_class()
        with pytest.raises(DestructiveExpandError):
            await run_phase(db, [migration], "expand")

    async def test_the_failed_migration_is_not_recorded(self, db) -> None:
        with pytest.raises(DestructiveExpandError):
            await run_phase(db, [_DroppingExpand()], "expand")
        assert not await is_recorded(db, "9001_test", "expand")

    async def test_the_lock_is_released_after_a_failure(self, db) -> None:
        """Otherwise one bad migration wedges every future deploy."""
        with pytest.raises(DestructiveExpandError):
            await run_phase(db, [_DroppingExpand()], "expand")
        assert await db[LEDGER].find_one({"_id": LOCK_ID}) is None

    async def test_the_same_operations_are_allowed_in_migrate(self, db) -> None:
        """The guard is about the phase, not the operation — migrate may unset."""
        migration = _UnsettingExpand()
        await run_phase(db, [migration], "migrate")
        assert migration.ran == ["migrate"]


class TestContractOrdering:
    async def test_contract_refuses_before_its_own_migrate(self, db) -> None:
        with pytest.raises(ContractTooEarlyError, match="may not have moved"):
            await run_phase(db, [_Recorder()], "contract")

    async def test_contract_runs_once_migrate_is_recorded(self, db) -> None:
        migration = _Recorder()
        await run_phase(db, [migration], "migrate")
        await run_phase(db, [migration], "contract")
        assert migration.ran == ["migrate", "contract"]


class TestLock:
    async def test_a_held_lock_blocks_a_second_run(self, db) -> None:
        assert await acquire_lock(db)
        with pytest.raises(MigrationError, match="holds the lock"):
            await run_phase(db, ALL, "expand")
        await release_lock(db)

    async def test_a_stale_lock_is_broken(self, db) -> None:
        """A crashed run must not wedge every future deploy."""
        assert await acquire_lock(db)
        await db[LEDGER].update_one(
            {"_id": LOCK_ID},
            {"$set": {"acquired_at": dt.datetime.now(dt.UTC) - dt.timedelta(hours=2)}},
        )
        assert await acquire_lock(db)
        await release_lock(db)

    async def test_a_fresh_lock_is_not_broken(self, db) -> None:
        assert await acquire_lock(db)
        assert not await acquire_lock(db)
        await release_lock(db)


class TestPhaseNames:
    async def test_an_unknown_phase_is_rejected(self, db) -> None:
        with pytest.raises(MigrationError, match="unknown phase"):
            await run_phase(db, ALL, "shrink")
