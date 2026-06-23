import asyncio

from agents.agent_generator.agent import AgentGenerator, AgentGeneratorConfig
from agents.agent_generator.tools.response_validator import (
    ResponseValidationError,
    materialize_llm_response,
    validate_response,
)
from scripts.test_llm_generator import build_sample_ranked
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
    assert "Open the best link first" in response.message
    assert len(global_memory.cached) == 1
    assert len(behavioral_memory.recorded) == 1


def test_agent_generator_accepts_productive_llm_style_and_keeps_exact_facts() -> None:
    event = make_ranked()
    llm_message = (
        "INTRO: I found a couple of solid Samsung options that fit your budget.\n"
        "PRODUCT_HEADER: Best matches I found:\n"
        "PRICE_LABEL: Price\n"
        "SOURCE_LABEL: Store\n"
        "SCORE_LABEL: Match\n"
        "LINK_LABEL: Open\n"
        "BEST_REASON: The first option is the best balance because it has strong value and a trusted source.\n"
        "WHY_THIS_ORDER: The ranking favors better value and stronger trust signals.\n"
        "NEXT_STEP: Start with option #1, then verify the seller page before buying."
    )
    producer = FakeProducer()
    generator = make_generator(producer=producer, llm_client=FakeLlmClient(llm_message))

    response = asyncio.run(generator.handle_ranked(event))

    assert response is not None
    assert "solid Samsung options" in response.message
    assert "Best matches I found" in response.message
    assert "Store: jumia" in response.message
    assert "Match: 88/100" in response.message
    assert "Open: https://example.com/jumia-a15" in response.message
    assert "Samsung Galaxy A15 128GB" in response.message
    assert "2499 MAD" in response.message
    assert "https://example.com/jumia-a15" in response.message
    assert "Samsung Galaxy A05" in response.message
    assert "1890 MAD" in response.message
    assert "https://example.com/jumia-a05" in response.message
    assert "strong value" in response.message
    assert "ranking favors better value" in response.message
    assert "verify the seller page" in response.message


def test_materialize_llm_response_supports_darija_labels_and_human_sections() -> None:
    event = make_ranked()
    message = materialize_llm_response(
        event,
        (
            "INTRO: L9it lik had l-options li kaybano mzyanin 3la budget dyalk.\n"
            "PRODUCT_HEADER: Ahsen choices:\n"
            "PRICE_LABEL: Taman\n"
            "SOURCE_LABEL: Source\n"
            "SCORE_LABEL: Score\n"
            "LINK_LABEL: Lien\n"
            "BEST_REASON: Lwel kayban ahsen balance bin value w thiqa.\n"
            "WHY_THIS_ORDER: Ranking kaychof value, trust, quality w availability.\n"
            "NEXT_STEP: Bda b option #1 w verify seller qbel ma tchri."
        ),
        fallback_message="fallback",
    )

    assert "L9it lik" in message
    assert "Ahsen choices" in message
    assert "Taman: 2499 MAD" in message
    assert "Lien: https://example.com/jumia-a15" in message
    assert "Samsung Galaxy A15 128GB" in message
    assert "Lwel kayban" in message
    assert "verify seller" in message


def test_materialize_llm_response_supports_general_reply_without_products() -> None:
    event = DecisionRanked(
        request_id="req_hi",
        user_id="telegram_123",
        channel=Channel.WHATSAPP,
        products=[],
    )

    message = materialize_llm_response(
        event,
        "GENERAL_REPLY: Salam! Chno bghiti n9lleb lik 3lih? Ila 3tini product w budget n3awnk.",
        fallback_message="fallback",
    )

    assert message.startswith("Salam!")
    assert "budget" in message


def test_agent_generator_falls_back_when_llm_returns_unusable_unlabelled_text() -> None:
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


def test_llm_generator_script_sample_ranked_has_required_facts() -> None:
    event = build_sample_ranked()

    assert event.request_id == "req_llm_test"
    assert len(event.products) == 3
    assert event.products[0].title == "Samsung Galaxy A15 128GB"
    assert str(event.products[0].url) == "https://example.com/jumia-a15"
