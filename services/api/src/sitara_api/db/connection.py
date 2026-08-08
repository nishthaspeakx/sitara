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
    client: MongoClient = AsyncIOMotorClient(settings.mongodb_uri)
    return client, client[settings.mongo_db]


def make_redis(settings: Settings) -> Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)
