"""Tier 1: global shared memory backed by Redis.

This tier stores data that can be reused across users: product-query cache,
price history, site health, and robots.txt snapshots.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis

from agents.orchestrator.tools.cache_lookup import ProductCache, cache_key_for_query
from shared.events.schemas import PriceSnapshot, ProductQuery


class GlobalMemory:
    def __init__(self, redis: Redis, *, cache_ttl_seconds: int = 1800) -> None:
        self._redis = redis
        self._cache = ProductCache(redis, ttl_seconds=cache_ttl_seconds)

    async def get_cached_response(self, query: ProductQuery) -> str | None:
        return await self._cache.get(query)

    async def set_cached_response(self, query: ProductQuery, response: str) -> None:
        await self._cache.set(query, response)

    async def record_price_snapshot(self, snapshot: PriceSnapshot) -> None:
        key = f"prices:query:{cache_key_for_query(snapshot.query).removeprefix('products:query:')}"
        await self._redis.lpush(key, snapshot.model_dump_json())
        await self._redis.ltrim(key, 0, 99)

    async def get_price_history(self, query: ProductQuery, *, limit: int = 20) -> list[dict[str, Any]]:
        key = f"prices:query:{cache_key_for_query(query).removeprefix('products:query:')}"
        rows = await self._redis.lrange(key, 0, max(0, limit - 1))
        return [json.loads(row.decode("utf-8") if isinstance(row, bytes) else row) for row in rows]

    async def set_site_health(self, domain: str, status: str, *, metadata: dict[str, Any] | None = None) -> None:
        payload = {
            "domain": domain,
            "status": status,
            "metadata": metadata or {},
            "updated_at": datetime.now(UTC).isoformat(),
        }
        await self._redis.set(f"sites:{domain}:health", json.dumps(payload), ex=15 * 60)

    async def get_site_health(self, domain: str) -> dict[str, Any] | None:
        value = await self._redis.get(f"sites:{domain}:health")
        if value is None:
            return None
        return json.loads(value.decode("utf-8") if isinstance(value, bytes) else value)

    async def cache_robots_txt(self, domain: str, robots_txt: str, *, ttl_seconds: int = 6 * 60 * 60) -> None:
        await self._redis.set(f"sites:{domain}:robots", robots_txt, ex=ttl_seconds)

    async def get_robots_txt(self, domain: str) -> str | None:
        value = await self._redis.get(f"sites:{domain}:robots")
        if value is None:
            return None
        return value.decode("utf-8") if isinstance(value, bytes) else str(value)
