"""Build the database the §6.4 registry describes.

Idempotent by construction — safe to call on every boot and from the migration
runner. Three things happen per collection: the collection is created if absent,
its validator is applied (`collMod` when it already exists), and its indexes are
reconciled.

Index reconciliation is the only part that ever destroys anything. An index
whose name matches but whose options differ (M1 built `users.email` with a
`$type: "string"` partial filter, which stops matching the moment CSFLE turns
that field into `binData`) is dropped and rebuilt. Every drop is reported in the
returned `SchemaReport` rather than done silently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pymongo.errors import CollectionInvalid, OperationFailure

from sitara_api.db.connection import MongoDb
from sitara_api.db.registry import SPECS, CollectionSpec, IndexSpec, VectorIndexSpec
from sitara_api.db.validators import validator_options

# Server error codes we handle by name rather than by number-at-the-call-site.
_NAMESPACE_EXISTS = 48
_INDEX_OPTIONS_CONFLICT = 85
_INDEX_KEY_SPECS_CONFLICT = 86
_COMMAND_NOT_SUPPORTED = 59
_ATLAS_SEARCH_UNSUPPORTED = frozenset({_COMMAND_NOT_SUPPORTED, 40324, 115})


@dataclass
class SchemaReport:
    created_collections: list[str] = field(default_factory=list)
    created_indexes: list[str] = field(default_factory=list)
    rebuilt_indexes: list[str] = field(default_factory=list)
    vector_indexes: list[str] = field(default_factory=list)
    skipped_vector_indexes: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"{len(self.created_collections)} collections created, "
            f"{len(self.created_indexes)} indexes created, "
            f"{len(self.rebuilt_indexes)} rebuilt"
        )


def index_name(index: IndexSpec) -> str:
    """pymongo's naming convention, computed up front so the registry, the
    creator and the verifier all talk about an index by the same name."""
    if index.name:
        return index.name
    return "_".join(f"{key}_{direction}" for key, direction in index.keys)


def index_options(index: IndexSpec) -> dict[str, Any]:
    options: dict[str, Any] = {"name": index_name(index)}
    if index.unique:
        options["unique"] = True
    if index.partial is not None:
        options["partialFilterExpression"] = dict(index.partial)
    if index.ttl_seconds is not None:
        options["expireAfterSeconds"] = index.ttl_seconds
    return options


async def ensure_collection(db: MongoDb, spec: CollectionSpec, report: SchemaReport) -> None:
    options = validator_options(spec)
    try:
        await db.create_collection(spec.name, **options)
        report.created_collections.append(spec.name)
    except (CollectionInvalid, OperationFailure) as exc:
        # CollectionInvalid is pymongo's client-side pre-check; code 48 is the
        # server's. Both mean the same thing and both are the normal path on a
        # second run.
        if isinstance(exc, OperationFailure) and exc.code != _NAMESPACE_EXISTS:
            raise
        # Already there — bring its validator up to date in place.
        await db.command({"collMod": spec.name, **options})


async def ensure_index(
    db: MongoDb, spec: CollectionSpec, index: IndexSpec, report: SchemaReport
) -> None:
    name = index_name(index)
    label = f"{spec.name}.{name}"
    keys = list(index.keys)
    options = index_options(index)
    try:
        await db[spec.name].create_index(keys, **options)
        report.created_indexes.append(label)
    except OperationFailure as exc:
        if exc.code not in (_INDEX_OPTIONS_CONFLICT, _INDEX_KEY_SPECS_CONFLICT):
            raise
        # Same name, different options (or same keys under another name). The
        # registry is the source of truth, so the live index yields to it.
        await _drop_conflicting(db, spec, index)
        await db[spec.name].create_index(keys, **options)
        report.rebuilt_indexes.append(label)


async def _drop_conflicting(db: MongoDb, spec: CollectionSpec, index: IndexSpec) -> None:
    wanted_name = index_name(index)
    wanted_keys = [list(pair) for pair in index.keys]
    async for existing in db[spec.name].list_indexes():
        name = existing["name"]
        if name == "_id_":
            continue
        same_name = name == wanted_name
        same_keys = [list(pair) for pair in existing["key"].items()] == wanted_keys
        if same_name or same_keys:
            await db[spec.name].drop_index(name)


async def ensure_vector_index(
    db: MongoDb, spec: CollectionSpec, vector: VectorIndexSpec, report: SchemaReport
) -> None:
    """Atlas Search vector index (§32.5).

    Community mongo has no `createSearchIndexes` command, and the dev stack runs
    Community. Failing there would make the whole schema build unusable locally,
    so an unsupported deployment is recorded and skipped — verify.py is where
    that becomes an error, and only on a deployment that does support it.
    """
    definition = {
        "fields": [
            {
                "type": "vector",
                "path": vector.field,
                "numDimensions": vector.dimensions,
                "similarity": vector.similarity,
            },
            *({"type": "filter", "path": f} for f in vector.filters),
        ]
    }
    try:
        await db.command(
            {
                "createSearchIndexes": spec.name,
                "indexes": [
                    {"name": vector.name, "type": "vectorSearch", "definition": definition}
                ],
            }
        )
        report.vector_indexes.append(f"{spec.name}.{vector.name}")
    except OperationFailure as exc:
        if exc.code in _ATLAS_SEARCH_UNSUPPORTED or "not supported" in str(exc).lower():
            report.skipped_vector_indexes.append(f"{spec.name}.{vector.name}")
            return
        if "already exists" in str(exc).lower() or "duplicate" in str(exc).lower():
            report.vector_indexes.append(f"{spec.name}.{vector.name}")
            return
        raise


async def ensure_schema(db: MongoDb, specs: tuple[CollectionSpec, ...] = SPECS) -> SchemaReport:
    """Create/reconcile every declared collection. Idempotent."""
    report = SchemaReport()
    for spec in specs:
        await ensure_collection(db, spec, report)
        for index in spec.indexes:
            await ensure_index(db, spec, index, report)
        if spec.vector_index is not None:
            await ensure_vector_index(db, spec, spec.vector_index, report)
    return report


async def supports_search_indexes(db: MongoDb) -> bool:
    """True on Atlas (and anything else exposing `$listSearchIndexes`)."""
    try:
        await db.command({"listSearchIndexes": "memories"})
    except OperationFailure as exc:
        if exc.code in _ATLAS_SEARCH_UNSUPPORTED or "not supported" in str(exc).lower():
            return False
        return True
    except Exception:  # pragma: no cover - transport-level, treat as unsupported
        return False
    return True
