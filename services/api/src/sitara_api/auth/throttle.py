"""§27 OTP throttling backstop: 5 verification fails → 15-minute lock, Redis.

Firebase enforces its own client-side OTP limits; this is the server-side
backstop at the token-exchange endpoint, keyed per caller. Keys hold NO PII
beyond a transport address (§13 — nothing user-identifying is logged).
"""

from sitara_api.config import Settings
from sitara_api.db import Redis

_FAILS = "auth:otp:fails:{key}"
_LOCK = "auth:otp:lock:{key}"


class OtpThrottle:
    def __init__(self, redis: Redis, settings: Settings) -> None:
        self._redis = redis
        self._max_fails = settings.otp_max_fails
        self._lock_seconds = settings.otp_lock_seconds

    async def is_locked(self, key: str) -> bool:
        return bool(await self._redis.exists(_LOCK.format(key=key)))

    async def record_failure(self, key: str) -> None:
        fails_key = _FAILS.format(key=key)
        count = await self._redis.incr(fails_key)
        if count == 1:
            await self._redis.expire(fails_key, self._lock_seconds)
        if count >= self._max_fails:
            await self._redis.set(_LOCK.format(key=key), "1", ex=self._lock_seconds)
            await self._redis.delete(fails_key)

    async def record_success(self, key: str) -> None:
        await self._redis.delete(_FAILS.format(key=key))
