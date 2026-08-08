"""Mongo + Redis client wiring.

The *shape* of the database lives in registry.py; this module only opens
connections. Kept separate so verify.py and the migration runner can build a
client without importing the whole schema layer.
"""

from typing import Any

import redis.asyncio as aioredis
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from sitara_api.config import Settings

MongoDb = AsyncIOMotorDatabase[dict[str, Any]]
MongoClient = AsyncIOMotorClient[dict[str, Any]]
Redis = aioredis.Redis


def make_mongo(settings: Settings) -> tuple[MongoClient, MongoDb]:
    # tz_aware: BSON stores UTC but the default codec hands back NAIVE
    # datetimes, so `read_back - datetime.now(dt.UTC)` raises TypeError. That
    # is a runtime crash waiting in every module that does date arithmetic on
    # a stored value — §32.4's decay hit it, and panchang's cache already
    # carried a local workaround for the same hazard. Fixed at the source.
    client: MongoClient = AsyncIOMotorClient(settings.mongodb_uri, tz_aware=True)
    return client, client[settings.mongo_db]


def make_redis(settings: Settings) -> Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)
