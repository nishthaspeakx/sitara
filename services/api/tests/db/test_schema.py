"""ensure_schema builds §6.4 and is safe to run repeatedly."""

from __future__ import annotations

import pytest

from sitara_api.db.registry import BY_NAME, SPECS
from sitara_api.db.schema import ensure_schema, index_name

pytestmark = pytest.mark.asyncio


async def _index_names(db, collection: str) -> set[str]:
    return {doc["name"] async for doc in db[collection].list_indexes()}


class TestBuild:
    async def test_every_declared_collection_exists(self, db) -> None:
        live = set(await db.list_collection_names())
        missing = sorted(s.name for s in SPECS if s.name not in live)
        assert not missing

    async def test_every_declared_index_exists(self, db) -> None:
        for spec in SPECS:
            live = await _index_names(db, spec.name)
            for index in spec.indexes:
                assert index_name(index) in live, f"{spec.name}.{index_name(index)}"

    async def test_ttl_indexes_land_only_where_declared(self, db) -> None:
        for spec in SPECS:
            live = {doc["name"]: doc async for doc in db[spec.name].list_indexes()}
            with_ttl = {n for n, d in live.items() if "expireAfterSeconds" in d}
            declared = {index_name(i) for i in spec.indexes if i.ttl_seconds is not None}
            assert with_ttl == declared, spec.name

    async def test_payments_has_no_ttl(self, db) -> None:
        """§6.4 keeps payments for eight years (tax). A TTL index here would be
        a silent, unrecoverable data-loss bug."""
        live = [doc async for doc in db.payments.list_indexes()]
        assert not any("expireAfterSeconds" in doc for doc in live)


class TestIdempotence:
    async def test_running_twice_changes_nothing(self, db) -> None:
        before = {s.name: await _index_names(db, s.name) for s in SPECS}
        report = await ensure_schema(db)
        after = {s.name: await _index_names(db, s.name) for s in SPECS}
        assert before == after
        assert not report.created_collections
        assert not report.rebuilt_indexes

    async def test_a_third_run_still_reports_nothing_new(self, db) -> None:
        await ensure_schema(db)
        report = await ensure_schema(db)
        assert not report.created_collections and not report.rebuilt_indexes


class TestExtendsM3:
    """M3 built panchang_cache, transit_cache and fact_adjudications. M4 must
    extend them, not re-create or drop what M3 relies on."""

    async def test_panchang_uniq_index_keeps_its_partial_filter(self, db) -> None:
        live = {doc["name"]: doc async for doc in db.panchang_cache.list_indexes()}
        index = live["uniq_date_geo_tradition_panchang"]
        assert index["unique"] is True
        # §35.5 — scoped to panchang days so muhurat/festival rows may share the
        # collection under the other §7.2 key grammars.
        assert index["partialFilterExpression"] == {"kind": "panchang"}

    async def test_transit_uniq_index_carries_engine_semver(self, db) -> None:
        live = {doc["name"]: doc async for doc in db.transit_cache.list_indexes()}
        index = live["uniq_date_band_engine"]
        assert list(index["key"]) == ["date", "band", "engine_semver"]
        assert index["unique"] is True

    async def test_fact_adjudications_keeps_the_admin_queue_indexes(self, db) -> None:
        live = await _index_names(db, "fact_adjudications")
        assert {"status_1_created_at_1", "fact_key_1"} <= live


class TestReconciliation:
    async def test_an_index_with_stale_options_is_rebuilt(self, raw_db) -> None:
        """M1 built users.email with a `$type: "string"` partial filter, which
        stops matching the moment CSFLE turns that field into binData. The
        registry wins, and the rebuild is reported rather than silent."""
        await raw_db.users.create_index(
            [("email", 1)],
            unique=True,
            partialFilterExpression={"email": {"$type": "string"}},
            name="email_1",
        )
        report = await ensure_schema(raw_db)
        assert "users.email_1" in report.rebuilt_indexes

        live = {doc["name"]: doc async for doc in raw_db.users.list_indexes()}
        assert live["email_1"]["partialFilterExpression"] == {"email": {"$exists": True}}


class TestVectorIndex:
    async def test_community_mongo_reports_rather_than_fails(self, raw_db) -> None:
        """§32.5's index is an Atlas Search index. The dev stack is Community —
        the build must record that and carry on, or nobody can work locally."""
        report = await ensure_schema(raw_db)
        assert BY_NAME["memories"].vector_index is not None
        assert (
            "memories.memories_vector" in report.vector_indexes
            or "memories.memories_vector" in report.skipped_vector_indexes
        )
