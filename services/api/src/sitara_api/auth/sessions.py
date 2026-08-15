"""Backend sessions (§34.5/§22.5): opaque httpOnly cookie tokens, minted after
the one-time Firebase exchange. Access tokens live in Redis (fast lookup, TTL);
refresh tokens rotate on every use — a replayed old token is treated as theft
and kills the whole session.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from bson import ObjectId
from sitara_schemas import ErrorCode

from sitara_api import prototype
from sitara_api.config import Settings
from sitara_api.db import MongoDb, Redis
from sitara_api.errors import ApiError

ACCESS_COOKIE = "sitara_access"
REFRESH_COOKIE = "sitara_refresh"

_ACCESS_KEY = "auth:access:{digest}"


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class MintedSession:
    session_id: str
    access_token: str
    refresh_token: str


class SessionService:
    def __init__(self, db: MongoDb, redis: Redis, settings: Settings) -> None:
        self._db = db
        self._redis = redis
        self._settings = settings

    async def create(self, user_id: ObjectId, device_name: str | None) -> MintedSession:
        now = _now()
        refresh_token = secrets.token_urlsafe(48)
        doc: dict[str, Any] = {
            "user_id": user_id,
            "device_name": device_name or "unknown device",
            "refresh_hash": _digest(refresh_token),
            "prior_refresh_hashes": [],
            "refresh_expires_at": now + timedelta(seconds=self._settings.refresh_ttl_seconds),
            "revoked_at": None,
            "last_active_at": now,
            "created_at": now,
            "updated_at": now,
            "schema_v": 1,
        }
        result = await self._db.sessions.insert_one(doc)
        session_id = str(result.inserted_id)
        access_token = await self._mint_access(user_id, session_id)
        return MintedSession(session_id, access_token, refresh_token)

    async def _mint_access(self, user_id: ObjectId, session_id: str) -> str:
        access_token = secrets.token_urlsafe(32)
        await self._redis.set(
            _ACCESS_KEY.format(digest=_digest(access_token)),
            f"{user_id}:{session_id}",
            # `prototype.access_ttl_seconds`, not the raw setting: the Redis
            # TTL is the AUTHORITATIVE expiry and the cookie's max_age only
            # mirrors it, so widening one without the other would leave a
            # cookie the browser keeps and the server has already forgotten.
            ex=prototype.access_ttl_seconds(self._settings),
        )
        return access_token

    async def resolve_access(self, access_token: str) -> tuple[ObjectId, str] | None:
        raw = await self._redis.get(_ACCESS_KEY.format(digest=_digest(access_token)))
        if raw is None:
            return None
        value = raw.decode() if isinstance(raw, bytes) else str(raw)
        user_id, _, session_id = value.partition(":")
        session = await self._db.sessions.find_one(
            {"_id": ObjectId(session_id), "revoked_at": None}
        )
        if session is None:
            return None
        await self._db.sessions.update_one(
            {"_id": ObjectId(session_id)},
            {"$set": {"last_active_at": _now(), "updated_at": _now()}},
        )
        return ObjectId(user_id), session_id

    async def rotate(self, refresh_token: str) -> tuple[ObjectId, MintedSession]:
        digest = _digest(refresh_token)
        session = await self._db.sessions.find_one({"refresh_hash": digest})

        if session is None:
            # A rotated-away token? Replay = theft signal → revoke the session (§22.5).
            stolen = await self._db.sessions.find_one({"prior_refresh_hashes": digest})
            if stolen is not None:
                await self.revoke(str(stolen["_id"]))
            raise ApiError(ErrorCode.AUTH_SESSION_EXPIRED)

        expires_at = session["refresh_expires_at"]
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if session["revoked_at"] is not None or expires_at <= _now():
            raise ApiError(ErrorCode.AUTH_SESSION_EXPIRED)

        now = _now()
        new_refresh = secrets.token_urlsafe(48)
        await self._db.sessions.update_one(
            {"_id": session["_id"]},
            {
                "$set": {
                    "refresh_hash": _digest(new_refresh),
                    "refresh_expires_at": now
                    + timedelta(seconds=self._settings.refresh_ttl_seconds),
                    "last_active_at": now,
                    "updated_at": now,
                },
                "$push": {"prior_refresh_hashes": digest},
            },
        )
        access_token = await self._mint_access(session["user_id"], str(session["_id"]))
        return session["user_id"], MintedSession(str(session["_id"]), access_token, new_refresh)

    async def revoke(self, session_id: str) -> None:
        await self._db.sessions.update_one(
            {"_id": ObjectId(session_id)},
            {"$set": {"revoked_at": _now(), "updated_at": _now()}},
        )

    async def list_for_user(
        self, user_id: ObjectId, current_session_id: str
    ) -> list[dict[str, Any]]:
        cursor = self._db.sessions.find({"user_id": user_id, "revoked_at": None}).sort(
            "created_at", -1
        )
        sessions = []
        async for doc in cursor:
            sessions.append(
                {
                    "session_id": str(doc["_id"]),
                    "device_name": doc["device_name"],
                    "created_at": doc["created_at"].isoformat(),
                    "last_active_at": doc["last_active_at"].isoformat(),
                    "current": str(doc["_id"]) == current_session_id,
                }
            )
        return sessions
