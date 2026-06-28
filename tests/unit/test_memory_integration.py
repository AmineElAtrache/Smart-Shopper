"""Integration tests proving the three memory tiers work across agents."""

from __future__ import annotations

import asyncio

import pytest

from agents.ambient_scheduler.scheduler import AmbientScheduler
from agents.orchestrator.agent import OrchestratorAgent
from agents.orchestrator.service import OrchestratorService
from agents.orchestrator.tools.cache_lookup import ProductCache, cache_key_for_query
from shared.config import Settings
from shared.events.schemas import (
    AmbientWatch,
    Channel,
    InboundMessage,
    ProductQuery,
)
from shared.events.topics import RESPONSE_OUTBOUND, SCRAPE_TASK_ASSIGNED
from shared.memory import GlobalMemory, UserMemory
from tests.unit.test_memory_tiers import FakeDatabase, FakeRedis


class FakeProducer:
    def __init__(self) -> None:
        self.published: list[tuple[str, object, object | None]] = []

    async def publish(self, topic, event, key=None) -> None:
        self.published.append((topic, event, key))


class FakeConsumer:
    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None


class FakeCollection:
    def __init__(self) -> None:
        self.docs: dict[str, dict] = {}

    def create_index(self, *args, **kwargs) -> None:
        return None

    def update_one(self, query, update, upsert=False) -> None:
        watch_id = query["watch_id"]
        document = self.docs.get(watch_id, {})
        document.update(query)
        document.update(update.get("$set", {}))
        self.docs[watch_id] = document

    def find_one(self, query):
        watch_id = query.get("watch_id")
        if watch_id is None:
            return None
        document = self.docs.get(watch_id)
        if document is None:
            return None
        if all(document.get(key) == value for key, value in query.items()):
            return document
        return None

    def find(self, query):
        del query
        return list(self.docs.values())


@pytest.mark.asyncio
async def test_tier_1_generator_cache_is_readable_by_orchestrator_product_cache() -> None:
    """GlobalMemory and Orchestrator ProductCache must share the same Redis keys."""
    redis = FakeRedis()
    global_memory = GlobalMemory(redis)
    orchestrator_cache = ProductCache(redis)
    query = ProductQuery(product="phone", brand="Samsung", budget=3000, city="fes")

    await global_memory.set_cached_response(query, "Shared tier-1 cached shopping reply")

    assert await orchestrator_cache.get(query) == "Shared tier-1 cached shopping reply"


def test_cache_key_ignores_routed_sites() -> None:
    base = ProductQuery(product="phone", brand="Samsung", budget=3000)
    routed = ProductQuery(
        product="phone",
        brand="Samsung",
        budget=3000,
        sites=["jumia", "avito", "electrosalam"],
    )

    assert cache_key_for_query(base) == cache_key_for_query(routed)


def test_tier_1_orchestrator_returns_cache_hit_without_scraping() -> None:
    """Tier 1 cache should short-circuit the pipeline at the orchestrator."""
    redis = FakeRedis()
    cache = ProductCache(redis)
    query = ProductQuery(product="phone", brand="Samsung", budget=3000)
    asyncio.run(cache.set(query, "Cached Samsung reply from tier 1"))

    settings = Settings(_env_file=None)
    producer = FakeProducer()
    db = FakeDatabase()
    user_memory = UserMemory(mongo_database=db, redis=redis)
    service = OrchestratorService(
        settings,
        agent=OrchestratorAgent(),
        cache=cache,
        user_memory=user_memory,
        consumer=FakeConsumer(),
        producer=producer,
    )

    message = InboundMessage(
        request_id="req_cache_hit",
        user_id="telegram_123",
        channel=Channel.TELEGRAM,
        text="Bghit Samsung phone b 3000 dh",
    )
    asyncio.run(service.handle_message(message))

    topics = [published[0] for published in producer.published]
    assert RESPONSE_OUTBOUND in topics
    assert SCRAPE_TASK_ASSIGNED not in topics
    assert producer.published[-1][1].message == "Cached Samsung reply from tier 1"


@pytest.mark.asyncio
async def test_tier_2_orchestrator_applies_saved_user_preferences() -> None:
    """Tier 2 preferences stored by orchestrator should enrich later searches."""
    redis = FakeRedis()
    db = FakeDatabase()
    user_memory = UserMemory(mongo_database=db, redis=redis)
    settings = Settings(_env_file=None)
    producer = FakeProducer()
    service = OrchestratorService(
        settings,
        agent=OrchestratorAgent(),
        cache=ProductCache(redis),
        user_memory=user_memory,
        consumer=FakeConsumer(),
        producer=producer,
    )

    first_message = InboundMessage(
        request_id="req_pref_1",
        user_id="telegram_456",
        channel=Channel.TELEGRAM,
        text="Bghit phone f fes b 2500 dh",
    )
    await service.handle_message(first_message)

    scrape_events = [event for topic, event, _ in producer.published if topic == SCRAPE_TASK_ASSIGNED]
    assert scrape_events
    assert scrape_events[-1].query.city == "fes"
    assert scrape_events[-1].query.budget == 2500

    profile = await user_memory.get_profile("telegram_456")
    assert profile.preferred_city == "fes"
    assert profile.preferred_budget == 2500

    same_product = await user_memory.apply_preferences(
        "telegram_456",
        ProductQuery(product="phone"),
    )
    assert same_product.city == "fes"
    assert same_product.budget == 2500

    different_product = await user_memory.apply_preferences(
        "telegram_456",
        ProductQuery(product="laptop"),
    )
    assert different_product.city == "fes"
    assert different_product.budget is None

    jumia_only = await user_memory.apply_preferences(
        "telegram_456",
        ProductQuery(product="phone", sites=["jumia"]),
    )
    assert jumia_only.city is None


@pytest.mark.asyncio
async def test_tier_2_ambient_scheduler_persists_watch_in_user_memory() -> None:
    """Ambient watches should be mirrored into tier-2 user memory."""
    db = FakeDatabase()
    user_memory = UserMemory(mongo_database=db, redis=FakeRedis())
    settings = Settings(_env_file=None)
    scheduler = AmbientScheduler(
        settings,
        watch_consumer=FakeConsumer(),
        ranked_consumer=FakeConsumer(),
        producer=FakeProducer(),
        user_memory=user_memory,
    )
    scheduler._collection = FakeCollection()

    watch = AmbientWatch(
        request_id="watch_001",
        user_id="telegram_789",
        channel=Channel.TELEGRAM,
        query=ProductQuery(product="phone", brand="Samsung", budget=3000),
    )
    await scheduler.handle_watch(watch)

    saved = db["user_watches"].find_one({"user_id": "telegram_789", "watch_id": "watch_001"})
    assert saved is not None
    assert saved["query"]["product"] == "phone"
    assert saved["status"] == "active"


def test_tier_3_behavioral_memory_is_not_used_by_orchestrator_orchestrator_path() -> None:
    """Tier 3 remains generator-private; orchestrator path should not require it."""
    redis = FakeRedis()
    settings = Settings(_env_file=None)
    producer = FakeProducer()
    service = OrchestratorService(
        settings,
        agent=OrchestratorAgent(),
        cache=ProductCache(redis),
        user_memory=None,
        consumer=FakeConsumer(),
        producer=producer,
    )

    message = InboundMessage(
        request_id="req_no_behavior",
        user_id="telegram_999",
        channel=Channel.TELEGRAM,
        text="Bghit Samsung phone b 3000 dh",
    )
    asyncio.run(service.handle_message(message))

    topics = [published[0] for published in producer.published]
    assert SCRAPE_TASK_ASSIGNED in topics
