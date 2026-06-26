"""robots.txt policy checker with Redis caching."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
from redis.asyncio import Redis

from shared.memory.global_memory import GlobalMemory


@dataclass(frozen=True)
class RobotsDecision:
    allowed: bool
    domain: str
    robots_url: str
    reason: str


class RobotsChecker:
    def __init__(
        self,
        redis: Redis,
        *,
        ttl_seconds: int = 6 * 60 * 60,
        global_memory: GlobalMemory | None = None,
    ) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds
        self._global_memory = global_memory

    async def can_fetch(self, url: str, *, user_agent: str = "SmartShopperBot") -> RobotsDecision:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if not domain:
            return RobotsDecision(False, "", "", "invalid_url")

        robots_url = f"{parsed.scheme or 'https'}://{domain}/robots.txt"
        robots_txt = await self._get_robots_txt(robots_url)
        if robots_txt is None:
            return RobotsDecision(True, domain, robots_url, "robots_unavailable_allow")

        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(robots_txt.splitlines())
        allowed = parser.can_fetch(user_agent, url)
        return RobotsDecision(allowed, domain, robots_url, "allowed" if allowed else "disallowed")

    async def _get_robots_txt(self, robots_url: str) -> str | None:
        domain = urlparse(robots_url).netloc.lower()
        if domain and self._global_memory is not None:
            cached = await self._global_memory.get_robots_txt(domain)
            if cached is not None:
                return cached

        key = f"robots:{robots_url}"
        cached = await self._redis.get(key)
        if cached is not None:
            robots_txt = cached.decode("utf-8") if isinstance(cached, bytes) else str(cached)
            if domain and self._global_memory is not None:
                await self._global_memory.cache_robots_txt(
                    domain,
                    robots_txt,
                    ttl_seconds=self._ttl_seconds,
                )
            return robots_txt

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(robots_url)
                if response.status_code >= 400:
                    return None
                robots_txt = response.text
                await self._redis.set(key, robots_txt, ex=self._ttl_seconds)
                if domain and self._global_memory is not None:
                    await self._global_memory.cache_robots_txt(
                        domain,
                        robots_txt,
                        ttl_seconds=self._ttl_seconds,
                    )
                return robots_txt
        except httpx.HTTPError:
            return None
