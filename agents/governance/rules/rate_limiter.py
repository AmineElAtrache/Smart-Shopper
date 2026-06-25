"""Redis-backed fixed-window rate limiter."""

from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    key: str
    count: int
    limit: int
    window_seconds: int


class RateLimiter:
    def __init__(self, redis: Redis, *, limit: int, window_seconds: int = 60) -> None:
        self._redis = redis
        self._limit = limit
        self._window_seconds = window_seconds

    async def check(self, scope: str, identifier: str) -> RateLimitDecision:
        key = f"rate:{scope}:{identifier}"
        count = int(await self._redis.incr(key))
        if count == 1:
            await self._redis.expire(key, self._window_seconds)
        return RateLimitDecision(
            allowed=count <= self._limit,
            key=key,
            count=count,
            limit=self._limit,
            window_seconds=self._window_seconds,
        )
