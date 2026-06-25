"""WebScraping Agent for the Smart Shopper MVP.

The agent now tries real scraper providers first and falls back to deterministic
mock products when providers fail or return no products.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

from agents.webscraping.spiders import (
    avito,
    biougnach,
    decathlon,
    defacto,
    electroplanet,
    electrosalam,
    ikea,
    jumia,
    mafiawaystore,
    marjane,
    moteur,
    mubawab,
    mymarket,
    ultrapc,
)
from shared.config.env import load_env_file
from shared.config import get_settings
from shared.events.kafka import KafkaEventConsumer, KafkaEventProducer
from shared.events.schemas import Availability, DecisionRanked, RawProduct, ScrapeTaskAssigned
from shared.events.topics import DECISION_RANKED, SCRAPE_RAW, SCRAPE_TASK_ASSIGNED
from shared.runtime import HealthServer

DEFAULT_KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"

SCRAPE_PROVIDERS = (
    ("jumia", jumia),
    ("avito", avito),
    ("electrosalam", electrosalam),
    ("mafiawaystore", mafiawaystore),
    ("moteur", moteur),
    ("mymarket", mymarket),
    ("ultrapc", ultrapc),
    ("electroplanet", electroplanet),
    ("defacto", defacto),
    ("biougnach", biougnach),
    ("marjane", marjane),
    ("decathlon", decathlon),
    ("mubawab", mubawab),
    ("ikea", ikea),
)


def build_mock_products(task: ScrapeTaskAssigned) -> list[RawProduct]:
    """Create deterministic product results from a scraping task."""
    query = task.query
    brand = query.brand or "Samsung"
    product = query.product or "phone"
    budget = query.budget or 3000
    currency = query.currency

    best_price = max(1, round(budget * 0.83))
    avito_price = round(budget * 1.10)
    budget_price = max(1, round(budget * 0.63))

    return [
        RawProduct(
            request_id=task.request_id,
            user_id=task.user_id,
            channel=task.channel,
            query=query,
            source="jumia",
            title=f"{brand} Galaxy A15 128GB {product}",
            price=best_price,
            currency=currency,
            url="https://example.com/jumia-a15",
            availability=Availability.IN_STOCK,
            seller="Jumia official",
            rating=4.5,
            metadata={"mock": True, "rank_hint": "best"},
        ),
        RawProduct(
            request_id=task.request_id,
            user_id=task.user_id,
            channel=task.channel,
            query=query,
            source="avito",
            title=f"{brand} Galaxy A15 {product}",
            price=avito_price,
            currency=currency,
            url="https://example.com/avito-a15",
            availability=Availability.UNKNOWN,
            seller="Private seller",
            rating=3.5,
            metadata={"mock": True},
        ),
        RawProduct(
            request_id=task.request_id,
            user_id=task.user_id,
            channel=task.channel,
            query=query,
            source="jumia",
            title=f"{brand} Galaxy A05 {product}",
            price=budget_price,
            currency=currency,
            url="https://example.com/jumia-a05",
            availability=Availability.IN_STOCK,
            seller="Jumia",
            rating=4.1,
            metadata={"mock": True, "rank_hint": "budget"},
        ),
    ]


async def _scrape_provider(
    provider_name: str,
    provider: object,
    task: ScrapeTaskAssigned,
    *,
    timeout_seconds: float,
) -> list[RawProduct]:
    try:
        try:
            scrape_call = provider.scrape(task, timeout=timeout_seconds)  # type: ignore[attr-defined]
        except TypeError:
            scrape_call = provider.scrape(task)  # type: ignore[attr-defined]
        provider_products = await asyncio.wait_for(
            scrape_call,
            timeout=timeout_seconds,
        )
    except TimeoutError:
        print(
            f"[scraper] {provider_name} timed out after {timeout_seconds}s "
            f"for {task.request_id}"
        )
        return []
    except Exception as exc:
        print(f"[scraper] {provider_name} failed for {task.request_id}: {exc}")
        return []

    if provider_products:
        print(
            f"[scraper] {provider_name} returned "
            f"{len(provider_products)} products for {task.request_id}"
        )
    return provider_products


async def scrape_products(
    task: ScrapeTaskAssigned,
    *,
    mock_only: bool = False,
    timeout_seconds: float = 30.0,
    max_concurrency: int = 8,
) -> list[RawProduct]:
    """Scrape providers concurrently, then fall back to mock products if needed."""
    if mock_only:
        fallback = build_mock_products(task)
        print(f"[scraper] mock-only mode; returning {len(fallback)} products for {task.request_id}")
        return fallback

    semaphore = asyncio.Semaphore(max_concurrency)

    async def bounded(provider_name: str, provider: object) -> list[RawProduct]:
        async with semaphore:
            return await _scrape_provider(
                provider_name,
                provider,
                task,
                timeout_seconds=timeout_seconds,
            )

    pending = [
        asyncio.create_task(bounded(provider_name, provider))
        for provider_name, provider in SCRAPE_PROVIDERS
    ]
    # Allow slow providers to finish even when others are still running.
    collection_timeout = timeout_seconds + 15.0
    done, still_running = await asyncio.wait(pending, timeout=collection_timeout)

    products: list[RawProduct] = []
    for finished in done:
        products.extend(finished.result())

    if still_running:
        print(
            f"[scraper] {len(still_running)} provider(s) still running after "
            f"{collection_timeout}s for {task.request_id}; cancelling remainder"
        )
    for running in still_running:
        running.cancel()
    if still_running:
        await asyncio.gather(*still_running, return_exceptions=True)

    if products:
        print(f"[scraper] collected {len(products)} products for {task.request_id}")
        return products

    if mock_only:
        fallback = build_mock_products(task)
        print(f"[scraper] mock-only mode; returning {len(fallback)} products for {task.request_id}")
        return fallback

    print(
        f"[scraper] no products collected for {task.request_id} "
        f"(finished={len(done)} cancelled={len(still_running)})"
    )
    return []

@dataclass(frozen=True)
class MockScraperConfig:
    kafka_bootstrap_servers: str = DEFAULT_KAFKA_BOOTSTRAP_SERVERS
    mock_only: bool = False
    timeout_seconds: float = 30.0
    max_concurrency: int = 8

    @classmethod
    def from_env(cls) -> "MockScraperConfig":
        load_env_file()
        mock_only = os.getenv("SCRAPE_MOCK_ONLY", "").lower() in {"1", "true", "yes"}
        return cls(
            kafka_bootstrap_servers=os.getenv(
                "KAFKA_BOOTSTRAP_SERVERS", DEFAULT_KAFKA_BOOTSTRAP_SERVERS
            ),
            mock_only=mock_only,
            timeout_seconds=float(os.getenv("SCRAPE_TIMEOUT_SECONDS", "30.0")),
            max_concurrency=int(os.getenv("SCRAPE_MAX_CONCURRENCY", "8")),
        )


class MockScraperAgent:
    def __init__(
        self,
        *,
        config: MockScraperConfig,
        producer: KafkaEventProducer | None = None,
    ) -> None:
        self._config = config
        self._producer = producer or KafkaEventProducer(
            config.kafka_bootstrap_servers,
            client_id="mock-scraper-agent",
        )

    async def handle_task(self, task: ScrapeTaskAssigned) -> list[RawProduct]:
        products = await scrape_products(
            task,
            mock_only=self._config.mock_only,
            timeout_seconds=self._config.timeout_seconds,
            max_concurrency=self._config.max_concurrency,
        )
        if not products:
            await self._publish_empty_ranked(task)
            return products
        for product in products:
            if task.watch_id:
                product.metadata["watch_id"] = task.watch_id
            if task.user_text:
                product.metadata["user_text"] = task.user_text
            await self._producer.publish(SCRAPE_RAW, product, key=task.request_id)
        return products

    async def _publish_empty_ranked(self, task: ScrapeTaskAssigned) -> None:
        ranked = DecisionRanked(
            request_id=task.request_id,
            user_id=task.user_id,
            channel=task.channel,
            query=task.query,
            products=[],
            user_text=task.user_text,
        )
        await self._producer.publish(DECISION_RANKED, ranked, key=task.request_id)
        print(
            f"[scraper] no products found; published empty decision.ranked "
            f"request_id={task.request_id}"
        )

    async def run(self) -> None:
        consumer = KafkaEventConsumer(
            SCRAPE_TASK_ASSIGNED,
            bootstrap_servers=self._config.kafka_bootstrap_servers,
            group_id="mock-scraper-agent",
            client_id="mock-scraper-agent",
        )

        await self._producer.start()
        await consumer.start()
        print("WebScraping agent started. Waiting for scrape.task.assigned events.")
        try:
            async for task in consumer.events(ScrapeTaskAssigned):
                products = await self.handle_task(task)
                print(f"Published {len(products)} products for {task.request_id}.")
        finally:
            await consumer.stop()
            await self._producer.stop()


async def main() -> None:
    settings = get_settings()
    health = HealthServer(host=settings.metrics_host, port=settings.metrics_port)
    await health.start()
    try:
        await MockScraperAgent(
            config=MockScraperConfig(
                kafka_bootstrap_servers=settings.kafka_bootstrap_servers,
                mock_only=settings.scrape_mock_only,
                timeout_seconds=settings.scrape_timeout_seconds,
                max_concurrency=settings.scrape_max_concurrency,
            )
        ).run()
    finally:
        await health.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("WebScraping agent stopped.")
