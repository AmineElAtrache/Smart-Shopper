import asyncio
from datetime import UTC, datetime, timedelta

from agents.ambient_scheduler.scheduler import AmbientScheduler, build_watch_notification
from shared.config import Settings
from shared.events.schemas import (
    AmbientWatch,
    Availability,
    Channel,
    DecisionRanked,
    ProductQuery,
    RankedProduct,
    ScoreBreakdown,
    WatchStatus,
)
from shared.events.topics import RESPONSE_OUTBOUND, SCRAPE_TASK_ASSIGNED


class FakeConsumer:
    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None


class FakeProducer:
    def __init__(self) -> None:
        self.published = []

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def publish(self, topic, event, key=None) -> None:
        self.published.append((topic, event, key))


class FakeCollection:
    def __init__(self) -> None:
        self.docs = {}

    def create_index(self, *args, **kwargs) -> None:
        return None

    def update_one(self, filter_doc, update_doc, upsert=False) -> None:
        watch_id = filter_doc["watch_id"]
        doc = self.docs.get(watch_id, {"watch_id": watch_id})
        doc.update(update_doc.get("$set", {}))
        self.docs[watch_id] = doc

    def find_one(self, filter_doc):
        doc = self.docs.get(filter_doc.get("watch_id"))
        if doc is None:
            return None
        status = filter_doc.get("status")
        if status is not None and doc.get("status") != status:
            return None
        return doc

    def find(self, filter_doc):
        now = filter_doc["next_run_at"]["$lte"]
        result = []
        for doc in self.docs.values():
            if doc.get("status") != filter_doc.get("status"):
                continue
            if doc.get("next_run_at") > now:
                continue
            expires_at = doc.get("expires_at")
            if expires_at is not None and expires_at <= datetime.now(UTC):
                continue
            result.append(doc)
        return result


def make_scheduler(collection: FakeCollection, producer: FakeProducer) -> AmbientScheduler:
    scheduler = AmbientScheduler(
        Settings(),
        watch_consumer=FakeConsumer(),
        ranked_consumer=FakeConsumer(),
        producer=producer,
    )
    scheduler._collection = collection
    return scheduler


def ranked_product(price: float, title: str = "HP Omen") -> RankedProduct:
    return RankedProduct(
        title=title,
        price=price,
        source="avito",
        url="https://example.com/hp-omen",
        availability=Availability.IN_STOCK,
        score=91,
        score_breakdown=ScoreBreakdown(price=35, trust=27, quality=20, availability=9),
    )



def test_ambient_watch_defaults_to_daily_interval_but_allows_premium_hourly_override() -> None:
    normal_watch = AmbientWatch(
        user_id="telegram_123",
        query=ProductQuery(product="laptop", brand="HP", budget=6000),
    )
    premium_watch = AmbientWatch(
        user_id="telegram_123",
        query=ProductQuery(product="laptop", brand="HP", budget=6000),
        interval_minutes=60,
    )

    assert normal_watch.interval_minutes == 1440
    assert premium_watch.interval_minutes == 60
def test_build_watch_notification_for_price_drop() -> None:
    message = build_watch_notification(product=ranked_product(5500), previous_price=6000)

    assert "Price drop detected" in message
    assert "Old best price: 6000 MAD" in message
    assert "New price: 5500 MAD" in message
    assert "Savings: 500 MAD" in message


def test_ambient_due_watch_emits_scrape_task_with_watch_id() -> None:
    collection = FakeCollection()
    producer = FakeProducer()
    scheduler = make_scheduler(collection, producer)
    collection.docs["watch_1"] = {
        "watch_id": "watch_1",
        "request_id": "watch_1",
        "user_id": "telegram_123",
        "channel": Channel.TELEGRAM,
        "query": ProductQuery(product="laptop", brand="HP", budget=6000).model_dump(),
        "interval_minutes": 60,
        "expires_at": datetime.now(UTC) + timedelta(days=1),
        "status": WatchStatus.ACTIVE,
        "next_run_at": datetime.now(UTC) - timedelta(seconds=1),
    }

    count = asyncio.run(scheduler.run_due_once())

    assert count == 1
    assert producer.published[0][0] == SCRAPE_TASK_ASSIGNED
    task = producer.published[0][1]
    assert task.watch_id == "watch_1"
    assert task.user_id == "telegram_123"


def test_ambient_ranked_result_sends_notification_for_new_best_price() -> None:
    collection = FakeCollection()
    producer = FakeProducer()
    scheduler = make_scheduler(collection, producer)
    collection.docs["watch_1"] = {
        "watch_id": "watch_1",
        "status": WatchStatus.ACTIVE,
        "last_best_price": 6000,
    }
    event = DecisionRanked(
        request_id="req_1",
        user_id="telegram_123",
        channel=Channel.TELEGRAM,
        watch_id="watch_1",
        query=ProductQuery(product="laptop", brand="HP", budget=6000),
        products=[ranked_product(5500), ranked_product(6200, title="HP Omen 2")],
    )

    response = asyncio.run(scheduler.handle_ranked(event))

    assert response is not None
    assert producer.published[0][0] == RESPONSE_OUTBOUND
    assert "Price drop detected" in response.message
    assert collection.docs["watch_1"]["last_best_price"] == 5500


def test_ambient_ranked_result_does_not_notify_when_price_is_not_better() -> None:
    collection = FakeCollection()
    producer = FakeProducer()
    scheduler = make_scheduler(collection, producer)
    collection.docs["watch_1"] = {
        "watch_id": "watch_1",
        "status": WatchStatus.ACTIVE,
        "last_best_price": 5000,
    }
    event = DecisionRanked(
        request_id="req_1",
        user_id="telegram_123",
        channel=Channel.TELEGRAM,
        watch_id="watch_1",
        products=[ranked_product(5500)],
    )

    response = asyncio.run(scheduler.handle_ranked(event))

    assert response is None
    assert producer.published == []
    assert collection.docs["watch_1"]["last_seen_price"] == 5500
