"""Smoke test real marketplace scraping without Kafka or Telegram."""

from __future__ import annotations

import asyncio
import sys

from agents.webscraping.agent import scrape_products
from shared.config import get_settings
from shared.events.schemas import Channel, ProductQuery, ScrapeTaskAssigned


async def main() -> None:
    settings = get_settings()
    text = " ".join(sys.argv[1:]).strip() or "Bghit Samsung phone b 3000 dh"
    task = ScrapeTaskAssigned(
        request_id="real_scrape_test",
        user_id="telegram_test",
        channel=Channel.TELEGRAM,
        user_text=text,
        query=ProductQuery(product="phone", brand="Samsung", budget=3000),
    )
    timeout = settings.scrape_timeout_seconds
    concurrency = settings.scrape_max_concurrency
    print(f"Scraping providers for: {text}")
    print(f"timeout={timeout}s concurrency={concurrency} (Playwright)")
    products = await scrape_products(
        task,
        mock_only=False,
        timeout_seconds=timeout,
        max_concurrency=concurrency,
    )
    real = [p for p in products if "example.com" not in str(p.url)]
    mock = len(products) - len(real)
    print(f"\nTotal={len(products)} real={len(real)} mock={mock}")
    if not real:
        print("No real products returned. Check network, Playwright, and scraper logs.")
        return
    for product in real[:5]:
        print(f"- {product.source}: {product.title[:70]} | {product.price:g} MAD")
        print(f"  {product.url}")


if __name__ == "__main__":
    asyncio.run(main())
