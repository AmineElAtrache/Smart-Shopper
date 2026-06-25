"""Simple in-memory proxy rotator for scraper workers."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class ProxyConfig:
    url: str
    weight: int = 1


class ProxyRotator:
    def __init__(self, proxies: list[ProxyConfig] | None = None) -> None:
        weighted: list[str] = []
        for proxy in proxies or []:
            weighted.extend([proxy.url] * max(1, proxy.weight))
        self._proxies = deque(weighted)

    @classmethod
    def from_csv(cls, value: str | None) -> "ProxyRotator":
        proxies = [ProxyConfig(url=item.strip()) for item in (value or "").split(",") if item.strip()]
        return cls(proxies)

    def next_proxy(self) -> str | None:
        if not self._proxies:
            return None
        proxy = self._proxies.popleft()
        self._proxies.append(proxy)
        return proxy
