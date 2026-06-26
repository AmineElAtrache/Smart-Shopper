import pytest

from shared.events.schemas import (
    Availability,
    Channel,
    DecisionRanked,
    ProductQuery,
    RankedProduct,
    ScoreBreakdown,
)
from shared.memory import GlobalMemory
from shared.memory.tier1_hooks import (
    build_price_snapshots,
    provider_domain,
    record_provider_health,
    record_ranked_prices,
)
from tests.unit.test_memory_tiers import FakeRedis


@pytest.mark.asyncio
async def test_record_provider_health_marks_healthy_provider() -> None:
    memory = GlobalMemory(FakeRedis())

    await record_provider_health(
        memory,
        "jumia",
        product_count=12,
        elapsed_ms=842.5,
    )

    health = await memory.get_site_health(provider_domain("jumia"))
    assert health is not None
    assert health["status"] == "healthy"
    assert health["metadata"]["product_count"] == 12


@pytest.mark.asyncio
async def test_record_provider_health_marks_timeout_provider() -> None:
    memory = GlobalMemory(FakeRedis())

    await record_provider_health(
        memory,
        "avito",
        product_count=0,
        elapsed_ms=30000.0,
        error="timeout",
    )

    health = await memory.get_site_health(provider_domain("avito"))
    assert health is not None
    assert health["status"] == "timeout"


def test_build_price_snapshots_limits_to_top_three() -> None:
    ranked = DecisionRanked(
        request_id="req_1",
        user_id="telegram_123",
        channel=Channel.TELEGRAM,
        query=ProductQuery(product="phone", brand="Samsung", budget=3000),
        products=[
            RankedProduct(
                title=f"Product {index}",
                price=1000 + index,
                source="jumia",
                url=f"https://www.jumia.ma/product-{index}",
                availability=Availability.IN_STOCK,
                score=80,
                score_breakdown=ScoreBreakdown(price=30, trust=20, quality=18, availability=8),
            )
            for index in range(5)
        ],
    )

    snapshots = build_price_snapshots(ranked)

    assert len(snapshots) == 3
    assert snapshots[0].title == "Product 0"


@pytest.mark.asyncio
async def test_record_ranked_prices_writes_global_price_history() -> None:
    memory = GlobalMemory(FakeRedis())
    ranked = DecisionRanked(
        request_id="req_1",
        user_id="telegram_123",
        channel=Channel.TELEGRAM,
        query=ProductQuery(product="phone", brand="Samsung", budget=3000),
        products=[
            RankedProduct(
                title="Samsung Galaxy A15",
                price=2499,
                source="jumia",
                url="https://www.jumia.ma/samsung-galaxy-a15",
                availability=Availability.IN_STOCK,
                score=88,
                score_breakdown=ScoreBreakdown(price=36, trust=27, quality=17, availability=8),
            )
        ],
    )

    snapshots = await record_ranked_prices(memory, ranked)

    assert len(snapshots) == 1
    history = await memory.get_price_history(ranked.query)
    assert history[0]["source"] == "jumia"
    assert history[0]["price"] == 2499
