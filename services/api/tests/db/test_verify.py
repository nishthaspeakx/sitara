"""`python -m sitara_api.db.verify` — the M4 acceptance command.

It has to be right in both directions: green on a correct database, and loud
and specific on a wrong one. A verifier that cannot fail is decoration.
"""

from __future__ import annotations

import pytest

from sitara_api.db.registry import SPECS
from sitara_api.db.verify import render, verify

pytestmark = pytest.mark.asyncio


class TestClean:
    async def test_a_correctly_built_database_passes(self, db) -> None:
        result = await verify(db)
        assert result.ok, render(result)

    async def test_the_report_names_every_declared_collection(self, db) -> None:
        output = render(await verify(db))
        for spec in SPECS:
            assert spec.name in output, spec.name

    async def test_the_report_cites_the_spec_for_each_collection(self, db) -> None:
        output = render(await verify(db))
        assert "[§6.4]" in output
        assert "[§25.7]" in output  # the collections the table does not list
        assert "[§22.5 / §34.5]" in output

    async def test_the_report_marks_stories_dark(self, db) -> None:
        """§30.6 — a P1 experiment must never read as shipped."""
        output = render(await verify(db))
        assert "P1 · dark" in output

    async def test_the_report_names_the_encrypted_fields(self, db) -> None:
        output = render(await verify(db))
        assert "csfle: date" in output  # birth_details

    async def test_the_report_names_declared_shard_keys(self, db) -> None:
        output = render(await verify(db))
        assert "shard: hashed(user_id) (Stage 3+)" in output


class TestDrift:
    async def test_a_missing_index_fails(self, db) -> None:
        await db.users.drop_index("locale_1_status_1")
        result = await verify(db)
        assert not result.ok
        assert any("locale_1_status_1 missing" in f.message for f in result.findings)
        assert "DRIFT" in render(result)

    async def test_an_undeclared_index_fails(self, db) -> None:
        """An index nobody declared is either dead weight or an out-of-band
        change — either way the registry has stopped being the source of truth."""
        await db.messages.create_index([("role", 1)], name="role_1")
        result = await verify(db)
        assert any("undeclared index role_1" in f.message for f in result.findings)

    async def test_an_index_with_changed_options_fails(self, db) -> None:
        await db.payments.drop_index("provider_event_id_1")
        await db.payments.create_index([("provider_event_id", 1)], name="provider_event_id_1")
        result = await verify(db)
        assert any("provider_event_id_1 options" in f.message for f in result.findings)

    async def test_a_missing_collection_fails(self, db) -> None:
        await db.drop_collection("goals")
        result = await verify(db)
        assert any(
            f.collection == "goals" and "does not exist" in f.message for f in result.findings
        )

    async def test_an_undeclared_collection_fails(self, db) -> None:
        await db.create_collection("shadow_ledger")
        result = await verify(db)
        assert any(f.collection == "shadow_ledger" for f in result.findings)
        assert "UNDECLARED COLLECTION" in render(result)

    async def test_a_missing_validator_fails(self, db) -> None:
        await db.command({"collMod": "consents", "validator": {}})
        result = await verify(db)
        assert any("no validator" in f.message for f in result.findings)

    async def test_a_ttl_index_on_a_retained_collection_fails(self, db) -> None:
        """The trap this whole rule exists for: eight years of tax records
        quietly deleted by an index someone added in a hurry."""
        await db.payments.create_index("created_at", expireAfterSeconds=86400, name="created_at_1")
        result = await verify(db)
        messages = " ".join(f.message for f in result.findings)
        assert "would delete data §6.4 retains" in messages
        assert "8 years (tax)" in messages


class TestExitCode:
    async def test_render_reports_no_drift_when_clean(self, db) -> None:
        assert "No drift" in render(await verify(db))

    async def test_render_lists_every_finding(self, db) -> None:
        await db.drop_collection("goals")
        await db.drop_collection("consents")
        output = render(await verify(db))
        assert "2 finding(s)" in output
        assert "goals" in output and "consents" in output
