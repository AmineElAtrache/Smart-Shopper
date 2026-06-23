import pytest

from shared.events.schemas import Channel, DecisionRanked, InboundMessage, OutboundResponse, ProductQuery
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
