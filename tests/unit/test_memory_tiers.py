import pytest

from agents.orchestrator.tools.cache_lookup import ProductCache
from shared.events.schemas import (
    Availability,
    Channel,
    DecisionRanked,
    InboundMessage,
    OutboundResponse,
    PriceSnapshot,
    ProductQuery,
    RankedProduct,
    ScoreBreakdown,
)
from shared.memory import BehavioralMemory, GlobalMemory, UserMemory


class FakeRedis:
    def __init__(self) -> None:
        self.values = {}
        self.lists = {}

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, ex=None):
        del ex
        self.values[key] = value

    async def lpush(self, key, value):
        self.lists.setdefault(key, []).insert(0, value)

    async def ltrim(self, key, start, end):
        self.lists[key] = self.lists.get(key, [])[start : end + 1]

    async def lrange(self, key, start, end):
        return self.lists.get(key, [])[start : end + 1]


class FakeUpdateResult:
    pass


class FakeCollection:
    def __init__(self) -> None:
        self.rows = []

    def create_index(self, *args, **kwargs):
        return None

    def find_one(self, query):
        for row in self.rows:
            if all(row.get(key) == value for key, value in query.items()):
                return row
        return None

    def insert_one(self, document):
        self.rows.append(document)
        return document

    def update_one(self, query, update, upsert=False):
        row = self.find_one(query)
        if row is None:
            if not upsert:
                return FakeUpdateResult()
            row = dict(query)
            self.rows.append(row)
        row.update(update.get("$setOnInsert", {}))
        row.update(update.get("$set", {}))
        return FakeUpdateResult()

    def find(self, query):
        del query
        return list(self.rows)


class FakeDatabase:
    def __init__(self) -> None:
        self.collections = {}

    def __getitem__(self, name):
        self.collections.setdefault(name, FakeCollection())
        return self.collections[name]


@pytest.mark.asyncio
async def test_tier_1_global_memory_caches_response_and_price_history() -> None:
    memory = GlobalMemory(FakeRedis())
    query = ProductQuery(product="phone", brand="Samsung", budget=3000)

    await memory.set_cached_response(query, "cached answer")

    assert await memory.get_cached_response(query) == "cached answer"


@pytest.mark.asyncio
async def test_tier_2_user_memory_records_search_and_applies_preferences() -> None:
    db = FakeDatabase()
    memory = UserMemory(mongo_database=db, redis=FakeRedis())
    message = InboundMessage(
        request_id="req_1",
        user_id="telegram_123",
        channel=Channel.TELEGRAM,
        text="Bghit Samsung phone f fes b 3000dh",
    )
    query = ProductQuery(product="phone", brand="Samsung", city="fes", budget=3000)

    await memory.record_search(message, query)
    enriched = await memory.apply_preferences("telegram_123", ProductQuery(product="phone"))

    assert enriched.city == "fes"
    assert enriched.budget == 3000
    assert db["user_history"].rows[0]["direction"] == "inbound"


@pytest.mark.asyncio
async def test_tier_2_user_memory_does_not_apply_budget_across_products() -> None:
    db = FakeDatabase()
    memory = UserMemory(mongo_database=db, redis=FakeRedis())
    message = InboundMessage(
        request_id="req_laptop",
        user_id="telegram_123",
        channel=Channel.TELEGRAM,
        text="bghit hp omen b 7000dh",
    )
    await memory.record_search(
        message,
        ProductQuery(product="omen", brand="HP", budget=7000),
    )

    enriched = await memory.apply_preferences(
        "telegram_123",
        ProductQuery(product="fridge"),
    )

    assert enriched.product == "fridge"
    assert enriched.budget is None


@pytest.mark.asyncio
async def test_tier_3_behavioral_memory_records_private_generator_profile() -> None:
    db = FakeDatabase()
    memory = BehavioralMemory(mongo_database=db)
    ranked = DecisionRanked(
        request_id="req_1",
        user_id="telegram_123",
        channel=Channel.TELEGRAM,
        query=ProductQuery(product="phone"),
        products=[],
    )
    response = OutboundResponse(
        request_id="req_1",
        user_id="telegram_123",
        channel=Channel.TELEGRAM,
        message="I found a good option.",
    )

    await memory.record_generation(ranked, response)
    context = await memory.build_generation_context("telegram_123")

    assert context["response_count"] == 1
    assert db["generator_interactions"].rows[0]["message"] == "I found a good option."


@pytest.mark.asyncio
async def test_tier_1_global_memory_tracks_price_history_site_health_and_robots() -> None:
    memory = GlobalMemory(FakeRedis())
    query = ProductQuery(product="phone", brand="Samsung", budget=3000)

    await memory.record_price_snapshot(
        PriceSnapshot(
            request_id="req_1",
            user_id="telegram_123",
            channel=Channel.TELEGRAM,
            query=query,
            source="jumia",
            title="Samsung Galaxy A15",
            price=2499,
            url="https://www.jumia.ma/samsung-galaxy-a15",
        )
    )
    await memory.set_site_health("jumia.ma", "healthy", metadata={"latency_ms": 120})
    await memory.cache_robots_txt("jumia.ma", "User-agent: *\nDisallow:")

    history = await memory.get_price_history(query, limit=1)
    health = await memory.get_site_health("jumia.ma")
    robots = await memory.get_robots_txt("jumia.ma")

    assert history[0]["source"] == "jumia"
    assert history[0]["price"] == 2499
    assert health is not None
    assert health["status"] == "healthy"
    assert robots is not None
    assert "User-agent" in robots


@pytest.mark.asyncio
async def test_tier_1_product_cache_and_global_memory_share_redis_keys() -> None:
    redis = FakeRedis()
    global_memory = GlobalMemory(redis)
    product_cache = ProductCache(redis)
    query = ProductQuery(product="phone", brand="Samsung", budget=3000)

    await global_memory.set_cached_response(query, "shared cache payload")

    assert await product_cache.get(query) == "shared cache payload"


@pytest.mark.asyncio
async def test_tier_2_user_memory_uses_redis_hot_profile_cache() -> None:
    db = FakeDatabase()
    redis = FakeRedis()
    memory = UserMemory(mongo_database=db, redis=redis)
    message = InboundMessage(
        request_id="req_hot",
        user_id="telegram_hot",
        channel=Channel.TELEGRAM,
        text="Bghit phone f casablanca b 4000dh",
    )
    query = ProductQuery(product="phone", city="casablanca", budget=4000)

    await memory.record_search(message, query)
    db["user_profiles"].rows.clear()

    profile = await memory.get_profile("telegram_hot")

    assert profile.preferred_city == "casablanca"
    assert profile.preferred_budget == 4000
    assert "user:telegram_hot:profile" in redis.values


@pytest.mark.asyncio
async def test_tier_2_user_memory_records_outbound_response_history() -> None:
    db = FakeDatabase()
    memory = UserMemory(mongo_database=db, redis=FakeRedis())
    response = OutboundResponse(
        request_id="req_out",
        user_id="telegram_123",
        channel=Channel.TELEGRAM,
        message="Here are 3 Samsung phones under 3000 MAD.",
    )

    await memory.record_response(response)

    assert db["user_history"].rows[-1]["direction"] == "outbound"
    assert "Samsung phones" in db["user_history"].rows[-1]["message"]


@pytest.mark.asyncio
async def test_tier_2_user_memory_save_watch() -> None:
    db = FakeDatabase()
    memory = UserMemory(mongo_database=db, redis=FakeRedis())

    await memory.save_watch(
        "telegram_123",
        {"watch_id": "watch_1", "status": "active", "query": {"product": "phone"}},
    )

    saved = db["user_watches"].find_one({"user_id": "telegram_123", "watch_id": "watch_1"})
    assert saved is not None
    assert saved["status"] == "active"


@pytest.mark.asyncio
async def test_tier_3_behavioral_memory_learns_language_and_preferred_sources() -> None:
    db = FakeDatabase()
    memory = BehavioralMemory(mongo_database=db)
    ranked = DecisionRanked(
        request_id="req_behavior",
        user_id="telegram_darija",
        channel=Channel.TELEGRAM,
        user_text="Bghit Samsung phone b 3000 dh",
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
            ),
            RankedProduct(
                title="Samsung Galaxy A05",
                price=1890,
                source="avito",
                url="https://www.avito.ma/samsung-galaxy-a05",
                availability=Availability.IN_STOCK,
                score=80,
                score_breakdown=ScoreBreakdown(price=30, trust=20, quality=18, availability=8),
            ),
        ],
    )
    response = OutboundResponse(
        request_id="req_behavior",
        user_id="telegram_darija",
        channel=Channel.TELEGRAM,
        message="Hahuma 2 khityarat.",
    )

    await memory.record_generation(ranked, response)
    context = await memory.build_generation_context("telegram_darija")

    assert context["response_count"] == 1
    assert context["language"] == "darija"
    assert context["preferred_sources"] == ["jumia", "avito"]
    assert db["generator_behavior_profiles"].rows[0]["tone"] in {"concise", "friendly", "detailed"}
