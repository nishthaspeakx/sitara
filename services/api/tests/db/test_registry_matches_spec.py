"""The registry must not drift from SPEC §6.4.

This test does not restate the table — it reads it. `spec_table.py` parses the
frozen markdown; every assertion below compares what we build against what the
table says, so an edit to either side that is not matched by the other fails CI
rather than quietly shipping a database the spec does not describe.
"""

from __future__ import annotations

import pytest

from sitara_api.db import registry
from sitara_api.db.spec_table import SPEC_PATH, SpecIndex, SpecRow, load_spec_rows

pytestmark = pytest.mark.skipif(
    not SPEC_PATH.exists(), reason="SPEC.md not reachable (installed-wheel layout)"
)


@pytest.fixture(scope="module")
def rows() -> dict[str, SpecRow]:
    return load_spec_rows()


def _spec_rows() -> dict[str, SpecRow]:
    return load_spec_rows() if SPEC_PATH.exists() else {}


def _normalise(cell: str) -> str:
    return " ".join(cell.replace("**", "").split())


def _spec_keys(index: registry.IndexSpec) -> tuple[str, ...]:
    return index.spec_keys or index.key_names


# --- coverage --------------------------------------------------------------


def test_every_spec_row_has_a_registry_entry(rows: dict[str, SpecRow]) -> None:
    missing = sorted(name for name in rows if name not in registry.BY_NAME)
    assert not missing, f"§6.4 rows with no registry entry: {missing}"


def test_every_registry_entry_citing_6_4_is_a_spec_row(rows: dict[str, SpecRow]) -> None:
    strays = sorted(s.name for s in registry.SPECS if s.spec_ref.startswith("§6.4"))
    assert [n for n in strays if n not in rows] == [], (
        "a collection claiming §6.4 provenance that the table does not list"
    )


def test_collections_outside_the_table_cite_their_own_section(
    rows: dict[str, SpecRow],
) -> None:
    """§6.4 is not the only source of collections — but silence is not a source."""
    for spec in registry.SPECS:
        if spec.name in rows:
            continue
        assert spec.spec_ref and spec.spec_ref != "§6.4", (
            f"{spec.name} is not a §6.4 row and must cite the section that mandates it"
        )


# --- per-row properties ----------------------------------------------------


@pytest.mark.parametrize("name", sorted(_spec_rows()))
def test_retention_matches_the_table(name: str, rows: dict[str, SpecRow]) -> None:
    assert _normalise(registry.BY_NAME[name].retention) == _normalise(rows[name].retention_cell)


@pytest.mark.parametrize("name", sorted(_spec_rows()))
def test_shard_key_matches_the_table(name: str, rows: dict[str, SpecRow]) -> None:
    assert registry.BY_NAME[name].shard_key == rows[name].shard_key


@pytest.mark.parametrize("name", sorted(_spec_rows()))
def test_encryption_marks_match_the_table(name: str, rows: dict[str, SpecRow]) -> None:
    spec, row = registry.BY_NAME[name], rows[name]
    assert bool(spec.encrypted) == row.encrypted, (
        f"{name}: §6.4 encryption cell is {row.encryption_cell!r} but the registry "
        f"declares {sorted(spec.encrypted_paths)}"
    )


@pytest.mark.parametrize("name", sorted(_spec_rows()))
def test_ttl_index_exists_exactly_where_the_table_says_ttl(
    name: str, rows: dict[str, SpecRow]
) -> None:
    """The load-bearing distinction: a TTL index on `payments` would delete the
    eight-year tax record §6.4 tells us to keep."""
    spec, row = registry.BY_NAME[name], rows[name]
    ttl_indexes = [i for i in spec.indexes if i.ttl_seconds is not None]
    if row.mandates_ttl_index:
        assert len(ttl_indexes) == 1, f"{name}: §6.4 says {row.retention_cell!r}"
    else:
        assert not ttl_indexes, (
            f"{name}: §6.4 retention is {row.retention_cell!r} — prose retention is a "
            f"job's problem, not a TTL index's"
        )


# --- indexes ---------------------------------------------------------------


def _matches(declared: registry.IndexSpec, wanted: SpecIndex) -> bool:
    if declared.unique != wanted.unique:
        return False
    if _spec_keys(declared) == wanted.keys:
        return True
    # An index may EXTEND a §6.4 key list (transit_cache adds engine_semver per
    # §7.2's key grammar) — only when it says so and cites why.
    return bool(declared.extends) and tuple(declared.extends) == wanted.keys


@pytest.mark.parametrize("name", sorted(_spec_rows()))
def test_every_index_the_table_names_is_built(name: str, rows: dict[str, SpecRow]) -> None:
    spec, row = registry.BY_NAME[name], rows[name]
    for wanted in row.indexes:
        if wanted.vector:
            assert spec.vector_index is not None, f"{name}: §6.4 names a vector index"
            assert spec.vector_index.dimensions == 1024  # §32.5
            assert spec.vector_index.similarity == "cosine"
            continue
        assert any(_matches(d, wanted) for d in spec.indexes), (
            f"{name}: §6.4 names index {wanted.raw!r} and the registry does not build it"
        )
        if wanted.partial_value is not None:
            matching = [d for d in spec.indexes if _matches(d, wanted)]
            assert any(d.partial for d in matching), (
                f"{name}: §6.4 writes {wanted.raw!r} — the trailing value needs a partial filter"
            )


@pytest.mark.parametrize("name", sorted(_spec_rows()))
def test_indexes_beyond_the_table_are_cited(name: str, rows: dict[str, SpecRow]) -> None:
    """Extra indexes are allowed. Unsourced ones are not."""
    spec, row = registry.BY_NAME[name], rows[name]
    wanted = [w for w in row.indexes if not w.vector]
    for declared in spec.indexes:
        if declared.ttl_seconds is not None and row.mandates_ttl_index:
            continue  # the TTL index the retention cell itself mandates
        if any(_matches(declared, w) for w in wanted) and not declared.extends:
            continue
        assert declared.cite, (
            f"{name}: index on {declared.key_names} is not in §6.4's cell "
            f"({row.indexes_cell!r}) and carries no citation"
        )


def test_transit_cache_extension_is_recorded_as_a_reconciliation(
    rows: dict[str, SpecRow],
) -> None:
    """§6.4 writes `uniq (date,band)`; §7.2's key grammar carries engine_v too.
    The reconciliation is CC-003 (§36.1) — assert it stays sourced, so nobody
    re-reads the extension later as an accident."""
    spec = registry.BY_NAME["transit_cache"]
    (uniq,) = [i for i in spec.indexes if i.unique]
    assert uniq.key_names == ("date", "band", "engine_semver")
    assert uniq.extends == ("date", "band") == rows["transit_cache"].indexes[0].keys
    assert uniq.cite and "§36.1" in uniq.cite


# --- rules that are not in the table but govern it -------------------------


def test_messages_carries_the_six_audio_fields() -> None:
    """§33.1's explicit field model — the reason voice-note replay is honest."""
    fields = registry.BY_NAME["messages"].fields
    for name in (
        "source_audio_asset_id",
        "tts_audio_asset_id",
        "transcript_status",
        "source_audio_expires_at",
        "source_audio_deleted_at",
        "playback_policy",
    ):
        assert name in fields, f"§33.1 requires messages.{name}"


def test_call_audio_has_nowhere_to_live() -> None:
    """§13/§33.1: live-call audio is never stored. Enforced structurally."""
    for name in ("voice_sessions", "call_sessions"):
        spec = registry.BY_NAME[name]
        assert spec.forbidden, f"{name} must forbid audio fields outright"
        assert not any("audio" in f for f in spec.all_fields), (
            f"{name} declares an audio field — §13 forbids storing call audio"
        )


def test_no_facts_collection_exists() -> None:
    """§34.2: fact-IDs are logical keys, not foreign keys. There is deliberately
    no `facts` collection, and adding one would break the snapshot model."""
    assert "facts" not in registry.BY_NAME


def test_a_unique_index_never_covers_a_randomized_field() -> None:
    """Randomized CSFLE gives the same plaintext a different ciphertext every
    time, so a unique index over it enforces nothing while still existing —
    a hollow index that reads as a guarantee. Uniqueness on an encrypted field
    is only real if that field is deterministic."""
    for spec in registry.SPECS:
        encrypted = {e.path: e for e in spec.encrypted}
        for index in spec.indexes:
            if not index.unique:
                continue
            for key in index.key_names:
                field = encrypted.get(key)
                assert field is None or field.deterministic, (
                    f"{spec.name}: unique index {index.key_names} covers {key!r}, which is "
                    "randomized-encrypted — the index cannot enforce uniqueness"
                )


def test_a_partial_filter_over_an_encrypted_field_matches_ciphertext() -> None:
    """The companion trap: `$type: "string"` stops matching the moment CSFLE
    turns the field into binData, and the unique index silently covers nothing.
    An encrypted field's partial filter must be type-agnostic."""
    for spec in registry.SPECS:
        for index in spec.indexes:
            if not index.partial:
                continue
            for key, condition in index.partial.items():
                if key not in spec.encrypted_paths:
                    continue
                assert isinstance(condition, dict) and "$type" not in condition, (
                    f"{spec.name}: the partial filter on encrypted field {key!r} tests "
                    "$type, which never matches ciphertext"
                )


def test_memory_embedding_is_not_encrypted() -> None:
    """§6.4 marks memories `field-level: content`. Encrypting the embedding as
    well would silently disable §32.5 vector retrieval — you cannot cosine-search
    ciphertext."""
    spec = registry.BY_NAME["memories"]
    assert spec.encrypted_paths == {"content"}
    assert spec.vector_index is not None


def test_stories_are_dark() -> None:
    """§30.6: P1 gated experiment. The collections exist (§25.7 dark launch);
    nothing may treat them as live."""
    assert registry.BY_NAME["stories"].dark
    assert registry.BY_NAME["story_views"].dark
