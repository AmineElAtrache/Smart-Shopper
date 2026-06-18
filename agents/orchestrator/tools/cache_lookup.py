"""Redis cache helper for product-query lookups."""

from __future__ import annotations

import hashlib

from redis.asyncio import Redis

from shared.events.schemas import ProductQuery


def cache_key_for_query(query: ProductQuery) -> str:
    fingerprint = query.model_dump_json()
    digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:16]
    return f"products:query:{digest}"


class ProductCache:
    def __init__(self, redis: Redis, ttl_seconds: int = 30 * 60) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds

    async def get(self, query: ProductQuery) -> str | None:
        value = await self._redis.get(cache_key_for_query(query))
        if value is None:
            return None
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)

    async def set(self, query: ProductQuery, payload: str) -> None:
        await self._redis.set(cache_key_for_query(query), payload, ex=self._ttl_seconds)
