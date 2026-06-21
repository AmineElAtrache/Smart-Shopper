"""Mock WebScraping Agent for the Smart Shopper MVP."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

from shared.config.env import load_env_file
from shared.events.kafka import KafkaEventConsumer, KafkaEventProducer
from shared.events.schemas import Availability, RawProduct, ScrapeTaskAssigned
from shared.events.topics import SCRAPE_RAW, SCRAPE_TASK_ASSIGNED

DEFAULT_KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"


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


@dataclass(frozen=True)
class MockScraperConfig:
    kafka_bootstrap_servers: str = DEFAULT_KAFKA_BOOTSTRAP_SERVERS

    @classmethod
    def from_env(cls) -> "MockScraperConfig":
        load_env_file()
        return cls(
            kafka_bootstrap_servers=os.getenv(
                "KAFKA_BOOTSTRAP_SERVERS", DEFAULT_KAFKA_BOOTSTRAP_SERVERS
            )
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
        products = build_mock_products(task)
        for product in products:
            await self._producer.publish(SCRAPE_RAW, product, key=task.request_id)
        return products

    async def run(self) -> None:
        consumer = KafkaEventConsumer(
            SCRAPE_TASK_ASSIGNED,
            bootstrap_servers=self._config.kafka_bootstrap_servers,
            group_id="mock-scraper-agent",
            client_id="mock-scraper-agent",
        )

        await self._producer.start()
        await consumer.start()
        print("Mock scraper agent started. Waiting for scrape.task.assigned events.")
        try:
            async for task in consumer.events(ScrapeTaskAssigned):
                products = await self.handle_task(task)
                print(f"Published {len(products)} mock products for {task.request_id}.")
        finally:
            await consumer.stop()
            await self._producer.stop()


async def main() -> None:
    await MockScraperAgent(config=MockScraperConfig.from_env()).run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Mock scraper agent stopped.")
