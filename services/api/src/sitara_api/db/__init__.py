"""The Sitara data layer — SPEC §6.4.

`registry.py` holds the §6.4 table as data; everything else reads it.
`ensure_indexes` is kept as the name M1 and M3 call at boot, now registry-driven.
"""

from sitara_api.db.connection import MongoClient, MongoDb, Redis, make_mongo, make_redis
from sitara_api.db.schema import SchemaReport, ensure_schema

__all__ = [
    "MongoClient",
    "MongoDb",
    "Redis",
    "SchemaReport",
    "ensure_indexes",
    "ensure_schema",
    "make_mongo",
    "make_redis",
]


async def ensure_indexes(db: MongoDb) -> None:
    """Build every §6.4 collection, validator and index.

    Kept under M1's name so callers do not change; the two hand-written index
    builders it replaces (`db.ensure_indexes`, `panchang.cache.ensure_panchang_indexes`)
    are gone — the registry is the only declaration now.
    """
    await ensure_schema(db)
