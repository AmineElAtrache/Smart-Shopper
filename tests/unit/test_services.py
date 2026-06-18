import asyncio

import pytest

from agents.decision.service import DecisionService
from agents.orchestrator.agent import OrchestratorAgent
from agents.orchestrator.service import OrchestratorService
from models.ner.grpc_server import NerService
from generated.ner.v1 import ner_pb2
from shared.config import Settings
from shared.events.schemas import Availability, InboundMessage, ProductQuery, RawProduct
from shared.events.topics import DECISION_RANKED, NER_EXTRACTED, SCRAPE_TASK_ASSIGNED


class FakeProducer:
    def __init__(self) -> None:
        self.published = []

    async def publish(self, topic, event, key=None) -> None:
        self.published.append((topic, event, key))


class EmptyCache:
    async def get(self, query):
        return None


class FakeConsumer:
    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None


def test_orchestrator_service_publishes_ner_and_scrape_task() -> None:
    settings = Settings()
    producer = FakeProducer()
    service = OrchestratorService(
        settings,
        agent=OrchestratorAgent(),
        cache=EmptyCache(),
        consumer=FakeConsumer(),
        producer=producer,
    )

    message = InboundMessage(
        request_id="req_001",
        user_id="telegram_123",
        text="Samsung phone under 3000 dh",
    )

    asyncio.run(service.handle_message(message))

    topics = [published[0] for published in producer.published]
    assert topics == [NER_EXTRACTED, SCRAPE_TASK_ASSIGNED]
    assert producer.published[1][1].query.brand == "Samsung"


def test_decision_service_flushes_ranked_products() -> None:
    settings = Settings(decision_batch_wait_seconds=0.01)
    producer = FakeProducer()
    service = DecisionService(settings, consumer=FakeConsumer(), producer=producer)

    query = ProductQuery(product="phone", brand="Samsung", budget=3000)
    product = RawProduct(
        request_id="req_001",
        user_id="telegram_123",
        query=query,
        source="jumia",
        title="Samsung Galaxy A15",
        price=2499,
        url="https://example.com/a15",
        availability=Availability.IN_STOCK,
        seller="Jumia official",
        rating=4.5,
    )
    service._pending["req_001"].append(product)

    asyncio.run(service.flush_request("req_001"))

    assert producer.published[0][0] == DECISION_RANKED
    ranked = producer.published[0][1]
    assert ranked.user_id == "telegram_123"
    assert ranked.products[0].source == "jumia"


@pytest.mark.asyncio
async def test_ner_grpc_service_extracts_entities() -> None:
    response = await NerService().Extract(
        ner_pb2.ExtractRequest(text="Bghit Samsung phone b 3000 dh", locale_hint="darija"),
        None,
    )

    values = {entity.type: entity.value for entity in response.entities}
    assert values["brand"] == "Samsung"
    assert values["product"] == "phone"
    assert values["budget"] == "3000.0"
