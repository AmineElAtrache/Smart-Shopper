"""Optional Scrapy runner wrapper used by structured scraper pools."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def run_spider(spider_cls: type, *, settings: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    try:
        from scrapy.crawler import CrawlerProcess
        from scrapy.signalmanager import dispatcher
        from scrapy import signals
    except ModuleNotFoundError as exc:
        raise RuntimeError("Install the scraping extra to run Scrapy spiders: pip install -e .[scraping]") from exc

    items: list[dict[str, Any]] = []

    def collect_item(item: dict[str, Any], response, spider) -> None:
        del response, spider
        items.append(dict(item))

    process = CrawlerProcess(settings=settings or {"LOG_ENABLED": False})
    dispatcher.connect(collect_item, signal=signals.item_scraped)
    process.crawl(spider_cls)
    process.start()
    return items


def ensure_scrapy_available(on_missing: Callable[[Exception], None] | None = None) -> bool:
    try:
        import scrapy  # noqa: F401
        return True
    except ModuleNotFoundError as exc:
        if on_missing is not None:
            on_missing(exc)
        return False
