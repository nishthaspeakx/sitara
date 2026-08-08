"""`python -m sitara_api.db.verify` — print the live database against §6.4 and
fail on drift.

The playbook's M4 acceptance line. It reads the registry (which the spec-parsing
test holds to §6.4) and the live database, prints one block per collection, and
exits non-zero on any of:

  · a declared collection that does not exist
  · a declared index that is missing, or present with different options
  · an index in the database that the registry does not declare
  · a missing validator
  · a TTL index on a collection §6.4 says to retain (the `payments` trap)
  · a missing TTL index where §6.4 mandates one
  · a collection in the database that the registry does not declare at all
  · a missing vector index, on a deployment that supports vector indexes

Extra indexes fail because an undeclared index is either dead weight nobody
owns or a change someone made outside the registry — and the registry stops
being the source of truth the moment either is tolerated.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass, field
from typing import Any

from sitara_api.config import Settings
from sitara_api.db.connection import MongoDb, make_mongo
from sitara_api.db.registry import EXEMPT_COLLECTIONS, SPECS, CollectionSpec, IndexSpec
from sitara_api.db.schema import index_name, index_options, supports_search_indexes

OK = "ok"
FAIL = "FAIL"


@dataclass
class Finding:
    collection: str
    message: str


@dataclass
class Verification:
    findings: list[Finding] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)

    def fail(self, collection: str, message: str) -> None:
        self.findings.append(Finding(collection, message))

    @property
    def ok(self) -> bool:
        return not self.findings


def _live_options(index: dict[str, Any]) -> dict[str, Any]:
    """Normalise a live index document down to the options we declare."""
    out: dict[str, Any] = {"name": index["name"]}
    if index.get("unique"):
        out["unique"] = True
    if "partialFilterExpression" in index:
        out["partialFilterExpression"] = dict(index["partialFilterExpression"])
    if "expireAfterSeconds" in index:
        out["expireAfterSeconds"] = index["expireAfterSeconds"]
    return out


def _key_tuple(keys: Any) -> tuple[tuple[str, Any], ...]:
    if isinstance(keys, dict):
        return tuple(keys.items())
    return tuple((k, v) for k, v in keys)


async def verify_collection(
    db: MongoDb,
    spec: CollectionSpec,
    live_names: set[str],
    result: Verification,
    *,
    search_supported: bool,
) -> None:
    tags = []
    if spec.dark:
        tags.append("P1 · dark")
    if spec.encrypted:
        tags.append(f"csfle: {', '.join(sorted(spec.encrypted_paths))}")
    if spec.shard_key:
        tags.append(f"shard: {spec.shard_key} (Stage 3+)")
    header = f"{spec.name}  [{spec.spec_ref}]" + (f"   {' · '.join(tags)}" if tags else "")

    if spec.name not in live_names:
        result.fail(spec.name, "collection does not exist")
        result.lines.append(f"{FAIL:>4}  {header}")
        return

    count = await db[spec.name].count_documents({})
    result.lines.append(f"{OK:>4}  {header}   ({count} docs) · retention: {spec.retention}")

    # --- validator
    cursor = await db.list_collections(filter={"name": spec.name})
    infos = await cursor.to_list(length=1)
    options = infos[0].get("options", {}) if infos else {}
    if not options.get("validator"):
        result.fail(spec.name, "no validator installed")
        result.lines.append(f"{FAIL:>4}    validator missing")
    else:
        result.lines.append(f"{OK:>4}    validator ({options.get('validationAction')})")

    # --- indexes
    live = {doc["name"]: doc async for doc in db[spec.name].list_indexes()}
    declared: dict[str, IndexSpec] = {index_name(i): i for i in spec.indexes}

    for name, index in declared.items():
        wanted = index_options(index)
        keys = _key_tuple(index.keys)
        detail = f"{name} {list(index.key_names)}"
        if index.unique:
            detail += " uniq"
        if index.ttl_seconds is not None:
            detail += f" ttl={index.ttl_seconds}s"
        if index.cite:
            detail += "  ← declared extra"

        if name not in live:
            result.fail(spec.name, f"index {name} missing")
            result.lines.append(f"{FAIL:>4}    {detail}  — MISSING")
            continue
        got = live[name]
        if _key_tuple(got["key"]) != keys:
            result.fail(spec.name, f"index {name} has keys {dict(got['key'])}, expected {keys}")
            result.lines.append(f"{FAIL:>4}    {detail}  — key mismatch {dict(got['key'])}")
            continue
        if _live_options(got) != wanted:
            result.fail(
                spec.name, f"index {name} options {_live_options(got)} != declared {wanted}"
            )
            result.lines.append(f"{FAIL:>4}    {detail}  — options {_live_options(got)}")
            continue
        result.lines.append(f"{OK:>4}    {detail}")

    for name in live:
        if name == "_id_" or name in declared:
            continue
        result.fail(spec.name, f"undeclared index {name} — not in the §6.4 registry")
        result.lines.append(f"{FAIL:>4}    {name}  — UNDECLARED")

    # --- TTL discipline (§6.4's retention column)
    has_ttl = any(i.ttl_seconds is not None for i in spec.indexes)
    mandates_ttl = spec.retention.strip().lower().startswith("ttl ")
    if mandates_ttl and not has_ttl:
        result.fail(spec.name, f"§6.4 says {spec.retention!r} but no TTL index is declared")
    if not mandates_ttl and has_ttl:
        result.fail(spec.name, f"TTL index on a collection §6.4 retains: {spec.retention!r}")
    live_ttl = [n for n, d in live.items() if "expireAfterSeconds" in d]
    if not mandates_ttl and live_ttl:
        result.fail(
            spec.name,
            f"live TTL index {live_ttl} would delete data §6.4 retains ({spec.retention!r})",
        )

    # --- vector index (§32.5)
    if spec.vector_index is not None:
        vector = spec.vector_index
        if not search_supported:
            result.lines.append(
                f"{'--':>4}    {vector.name} ({vector.dimensions}d {vector.similarity}) "
                "— vector search unavailable on this deployment"
            )
        else:
            names = [
                doc["name"]
                async for doc in db[spec.name].aggregate([{"$listSearchIndexes": {}}])
            ]
            if vector.name in names:
                result.lines.append(
                    f"{OK:>4}    {vector.name} ({vector.dimensions}d {vector.similarity})"
                )
            else:
                result.fail(spec.name, f"vector index {vector.name} missing (§32.5)")
                result.lines.append(f"{FAIL:>4}    {vector.name} — MISSING")


async def verify(db: MongoDb) -> Verification:
    result = Verification()
    live_names = set(await db.list_collection_names())
    search_supported = await supports_search_indexes(db)

    result.lines.append(f"SPEC §6.4 data layer · {len(SPECS)} declared collections")
    result.lines.append("")
    for spec in SPECS:
        await verify_collection(
            db, spec, live_names, result, search_supported=search_supported
        )
        result.lines.append("")

    undeclared = sorted(
        live_names - {s.name for s in SPECS} - EXEMPT_COLLECTIONS - {"system.views"}
    )
    for name in undeclared:
        result.fail(name, "collection exists but is not declared in the §6.4 registry")
        result.lines.append(f"{FAIL:>4}  {name}  — UNDECLARED COLLECTION")
    return result


def render(result: Verification) -> str:
    body = "\n".join(result.lines).rstrip()
    if result.ok:
        return f"{body}\n\nMatches §6.4. No drift."
    detail = "\n".join(f"  · {f.collection}: {f.message}" for f in result.findings)
    return f"{body}\n\nDRIFT — {len(result.findings)} finding(s):\n{detail}"


async def _run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sitara_api.db.verify")
    parser.add_argument("--quiet", action="store_true", help="print findings only")
    args = parser.parse_args(argv)

    settings = Settings()
    client, db = make_mongo(settings)
    try:
        result = await verify(db)
    finally:
        client.close()

    output = render(result)
    if args.quiet and result.ok:
        print("Matches §6.4. No drift.")
    else:
        print(output)
    return 0 if result.ok else 1


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(argv))


if __name__ == "__main__":
    sys.exit(main())
