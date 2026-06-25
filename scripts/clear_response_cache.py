"""Clear Redis product-response cache so E2E tests re-scrape instead of replaying mocks."""

from __future__ import annotations

import asyncio

from redis.asyncio import Redis

from shared.config import get_settings


async def main() -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        keys = [key async for key in redis.scan_iter("products:query:*")]
        if not keys:
            print("No product cache keys found.")
            return
        deleted = await redis.delete(*keys)
        print(f"Cleared {deleted} cached response key(s) from Redis.")
    finally:
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
