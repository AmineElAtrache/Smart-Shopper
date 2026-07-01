import asyncio

import pytest

from agents.decision.service import DecisionService
from agents.webscraping.agent import _scrape_provider
from shared.config import Settings
from shared.events.schemas import (
    Availability,
    Channel,
    ProductQuery,
    RawProduct,
    ScrapeTaskAssigned,
)
from shared.events.topics import DECISION_RANKED, PRICE_HISTORY
from shared.memory import GlobalMemory
from shared.memory.tier1_hooks import provider_domain
from tests.unit.test_memory_tiers import FakeRedis


class FakeProvider:
    async def scrape(self, task, timeout=None):
        return [
            RawProduct(
                request_id=task.request_id,
                source="jumia",
                title="Samsung Galaxy A15",
                price=2499,
                url="https://www.jumia.ma/samsung-galaxy-a15",
                availability=Availability.IN_STOCK,
            )
        ]


class FakeProducer:
    def __init__(self) -> None:
        self.published: list[tuple[str, object, object | None]] = []

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def publish(self, topic, event, key=None) -> None:
        self.published.append((topic, event, key))


class FakeConsumer:
    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None


@pytest.mark.asyncio
async def test_scraper_provider_records_tier1_site_health() -> None:
    memory = GlobalMemory(FakeRedis())
    task = ScrapeTaskAssigned(
        request_id="req_scrape",
        user_id="telegram_123",
        channel=Channel.TELEGRAM,
        query=ProductQuery(product="phone", brand="Samsung", budget=3000),
    )

    products = await _scrape_provider(
        "jumia",
        FakeProvider(),
        task,
        timeout_seconds=5.0,
        global_memory=memory,
    )

    assert len(products) == 1
    health = await memory.get_site_health(provider_domain("jumia"))
    assert health is not None
    assert health["status"] == "healthy"
    assert health["metadata"]["provider"] == "jumia"


def test_decision_service_records_tier1_price_history_and_kafka_event() -> None:
    memory = GlobalMemory(FakeRedis())
    producer = FakeProducer()
    settings = Settings(_env_file=None, decision_batch_wait_seconds=0.01)
    service = DecisionService(
        settings,
        consumer=FakeConsumer(),
        producer=producer,
        global_memory=memory,
    )

    product = RawProduct(
        request_id="req_decision",
        user_id="telegram_123",
        channel=Channel.TELEGRAM,
        query=ProductQuery(product="phone", brand="Samsung", budget=3000),
        source="jumia",
        title="Samsung Galaxy A15",
        price=2499,
        url="https://www.jumia.ma/samsung-galaxy-a15",
        availability=Availability.IN_STOCK,
        metadata={"user_text": "Bghit Samsung phone b 3000 dh"},
    )

    asyncio.run(service.handle_product(product))
    asyncio.run(service.flush_request("req_decision"))

    topics = [topic for topic, _, _ in producer.published]
    assert DECISION_RANKED in topics
    assert PRICE_HISTORY in topics

    history = asyncio.run(memory.get_price_history(product.query))
    assert history[0]["price"] == 2499
