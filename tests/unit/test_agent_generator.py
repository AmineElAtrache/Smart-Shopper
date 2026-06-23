import asyncio

from agents.agent_generator.agent import AgentGenerator, AgentGeneratorConfig
from agents.agent_generator.tools.response_validator import ResponseValidationError, validate_response
from shared.events.schemas import (
    Availability,
    Channel,
    DecisionRanked,
    ProductQuery,
    RankedProduct,
    ScoreBreakdown,
)
from shared.events.topics import RESPONSE_OUTBOUND


class FakeProducer:
    def __init__(self) -> None:
        self.published = []

    async def publish(self, topic, event, key=None) -> None:
        self.published.append((topic, event, key))


class FakeGlobalMemory:
    def __init__(self) -> None:
        self.cached = []

    async def set_cached_response(self, query, message) -> None:
        self.cached.append((query, message))


class FakeBehavioralMemory:
    def __init__(self) -> None:
        self.recorded = []

    async def build_generation_context(self, user_id):
        return {"tone": "concise", "language": "en", "user_id": user_id}

    async def record_generation(self, event, response) -> None:
        self.recorded.append((event, response))


class FakeLlmClient:
    def __init__(self, message: str) -> None:
        self.message = message

    async def generate_recommendation(self, event, fallback_message, *, behavior_context=None):
        return self.message


def make_ranked(*, watch_id: str | None = None) -> DecisionRanked:
    return DecisionRanked(
        request_id="req_001",
        user_id="telegram_123",
        channel=Channel.TELEGRAM,
        watch_id=watch_id,
        query=ProductQuery(product="phone", brand="Samsung", budget=3000),
        products=[
            RankedProduct(
                title="Samsung Galaxy A15 128GB",
                price=2499,
                source="jumia",
                url="https://example.com/jumia-a15",
                availability=Availability.IN_STOCK,
                score=88,
                score_breakdown=ScoreBreakdown(price=36, trust=27, quality=17, availability=8),
            ),
            RankedProduct(
                title="Samsung Galaxy A05",
                price=1890,
                source="jumia",
                url="https://example.com/jumia-a05",
                availability=Availability.IN_STOCK,
                score=84,
                score_breakdown=ScoreBreakdown(price=38, trust=24, quality=14, availability=8),
            ),
        ],
    )


def make_generator(**kwargs) -> AgentGenerator:
    return AgentGenerator(config=AgentGeneratorConfig(), **kwargs)


def test_response_validator_rejects_missing_product_facts() -> None:
    event = make_ranked()

    try:
        validate_response(event, "Buy this Samsung, it is cheap.")
    except ResponseValidationError as exc:
        assert "missing_price" in str(exc) or "missing_url" in str(exc)
    else:  # pragma: no cover - explicit failure readability
        raise AssertionError("validator accepted incomplete response")


def test_agent_generator_publishes_template_response_and_records_memory() -> None:
    producer = FakeProducer()
    global_memory = FakeGlobalMemory()
    behavioral_memory = FakeBehavioralMemory()
    generator = make_generator(
        producer=producer,
        global_memory=global_memory,
        behavioral_memory=behavioral_memory,
    )

    response = asyncio.run(generator.handle_ranked(make_ranked()))

    assert response is not None
    assert producer.published[0][0] == RESPONSE_OUTBOUND
    assert "Samsung Galaxy A15 128GB" in response.message
    assert "https://example.com/jumia-a15" in response.message
    assert len(global_memory.cached) == 1
    assert len(behavioral_memory.recorded) == 1


def test_agent_generator_accepts_valid_llm_response() -> None:
    event = make_ranked()
    llm_message = (
        "Best options:\n"
        "Samsung Galaxy A15 128GB - 2499 MAD - jumia - Score 88/100 - "
        "https://example.com/jumia-a15\n"
        "Samsung Galaxy A05 - 1890 MAD - jumia - Score 84/100 - "
        "https://example.com/jumia-a05"
    )
    producer = FakeProducer()
    generator = make_generator(producer=producer, llm_client=FakeLlmClient(llm_message))

    response = asyncio.run(generator.handle_ranked(event))

    assert response is not None
    assert response.message == llm_message


def test_agent_generator_falls_back_when_llm_drops_urls_or_prices() -> None:
    producer = FakeProducer()
    generator = make_generator(producer=producer, llm_client=FakeLlmClient("A nice Samsung option."))

    response = asyncio.run(generator.handle_ranked(make_ranked()))

    assert response is not None
    assert "A nice Samsung option" not in response.message
    assert "https://example.com/jumia-a15" in response.message
    assert "2499 MAD" in response.message


def test_agent_generator_skips_ambient_watch_ranked_events() -> None:
    producer = FakeProducer()
    generator = make_generator(producer=producer)

    response = asyncio.run(generator.handle_ranked(make_ranked(watch_id="watch_1")))

    assert response is None
    assert producer.published == []
