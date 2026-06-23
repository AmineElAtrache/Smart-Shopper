"""Dependency-free Prometheus text metrics for MVP services."""

from __future__ import annotations

from collections import defaultdict
from threading import Lock


class MetricsRegistry:
    def __init__(self) -> None:
        self._counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = {}
        self._lock = Lock()

    def increment(self, name: str, value: float = 1.0) -> None:
        with self._lock:
            self._counters[_sanitize(name)] += value

    def gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[_sanitize(name)] = value

    def render_prometheus(self) -> str:
        with self._lock:
            lines: list[str] = []
            for name, value in sorted(self._counters.items()):
                lines.append(f"# TYPE {name} counter")
                lines.append(f"{name} {value:g}")
            for name, value in sorted(self._gauges.items()):
                lines.append(f"# TYPE {name} gauge")
                lines.append(f"{name} {value:g}")
            return "\n".join(lines) + "\n"


def _sanitize(name: str) -> str:
    sanitized = "".join(character if character.isalnum() else "_" for character in name.lower())
    return sanitized.strip("_") or "smart_shopper_metric"


_DEFAULT_REGISTRY = MetricsRegistry()


def get_default_metrics() -> MetricsRegistry:
    return _DEFAULT_REGISTRY
