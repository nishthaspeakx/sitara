"""Mongo + Redis wiring (§6.4). Collections owned by M1: users, auth_identities,
sessions, link_conflicts. Index set mirrors the §6.4 table.
"""

from typing import Any

import redis.asyncio as aioredis
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING

from sitara_api.config import Settings

MongoDb = AsyncIOMotorDatabase[dict[str, Any]]
Redis = aioredis.Redis


def make_mongo(settings: Settings) -> tuple[AsyncIOMotorClient[dict[str, Any]], MongoDb]:
    client: AsyncIOMotorClient[dict[str, Any]] = AsyncIOMotorClient(settings.mongodb_uri)
    return client, client[settings.mongo_db]


def make_redis(settings: Settings) -> Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)


async def ensure_indexes(db: MongoDb) -> None:
    # users (§6.4): uniq firebase_uid; uniq email (sparse — phone-only users); locale+status.
    await db.users.create_index([("firebase_uid", ASCENDING)], unique=True)
    await db.users.create_index(
        [("email", ASCENDING)],
        unique=True,
        partialFilterExpression={"email": {"$type": "string"}},
    )
    await db.users.create_index([("locale", ASCENDING), ("status", ASCENDING)])
    await db.users.create_index(
        [("phone", ASCENDING)], partialFilterExpression={"phone": {"$type": "string"}}
    )

    # auth_identities (§6.4): uniq provider+provider_uid; user_id.
    await db.auth_identities.create_index(
        [("provider", ASCENDING), ("provider_uid", ASCENDING)], unique=True
    )
    await db.auth_identities.create_index([("user_id", ASCENDING)])

    # sessions (§22.5): refresh lookup by hash; per-user listing.
    await db.sessions.create_index([("refresh_hash", ASCENDING)])
    await db.sessions.create_index([("user_id", ASCENDING)])

    # link_conflicts (§32.12): one pending choose-flow per user at a time.
    await db.link_conflicts.create_index([("user_id", ASCENDING), ("status", ASCENDING)])
