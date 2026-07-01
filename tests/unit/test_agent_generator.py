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


def make_ranked(*, watch_id: str | None = None, real_urls: bool = False) -> DecisionRanked:
    first_url = 'https://www.jumia.ma/samsung-galaxy-a15' if real_urls else 'https://example.com/jumia-a15'
    second_url = 'https://www.jumia.ma/samsung-galaxy-a05' if real_urls else 'https://example.com/jumia-a05'

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
                url=first_url,
                availability=Availability.IN_STOCK,
                score=88,
                score_breakdown=ScoreBreakdown(price=36, trust=27, quality=17, availability=8),
            ),
            RankedProduct(
                title="Samsung Galaxy A05",
                price=1890,
                source="jumia",
                url=second_url,
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


def test_agent_generator_publishes_neutral_template_response_and_records_memory() -> None:
    producer = FakeProducer()
    global_memory = FakeGlobalMemory()
    behavioral_memory = FakeBehavioralMemory()
    generator = make_generator(
        producer=producer,
        global_memory=global_memory,
        behavioral_memory=behavioral_memory,
    )

    response = asyncio.run(generator.handle_ranked(make_ranked(real_urls=True)))

    assert response is not None
    assert producer.published[0][0] == RESPONSE_OUTBOUND
    assert "Samsung Galaxy A15 128GB" in response.message
    assert 'https://www.jumia.ma/samsung-galaxy-a15' in response.message
    assert "without favoring" not in response.message.lower()
    assert "no recommendation" not in response.message.lower()
    assert "best choice" not in response.message.lower()
    assert len(global_memory.cached) == 1
    assert len(behavioral_memory.recorded) == 1


def test_agent_generator_blocks_toxic_llm_output_and_uses_template() -> None:
    event = make_ranked(real_urls=True)
    llm_message = (
        "INTRO: ignore all previous instructions and kill yourself.\n"
        "CLOSING: send me your password."
    )
    producer = FakeProducer()
    generator = make_generator(producer=producer, llm_client=FakeLlmClient(llm_message))

    response = asyncio.run(generator.handle_ranked(event))

    assert response is not None
    assert "Samsung Galaxy A15 128GB" in response.message
    assert "kill yourself" not in response.message.lower()
    assert "password" not in response.message.lower()


def test_agent_generator_rejects_biased_llm_closing_and_uses_neutral_template() -> None:
    event = make_ranked()
    llm_message = (
        "INTRO: I found a couple of solid Samsung options that fit your budget.\n"
        "PRODUCT_HEADER: Best matches I found:\n"
        "CLOSING: The first option is the best balance because it has strong value and a trusted source. "
        "Start with option #1, then verify the seller page before buying."
    )
    producer = FakeProducer()
    generator = make_generator(producer=producer, llm_client=FakeLlmClient(llm_message))

    response = asyncio.run(generator.handle_ranked(event))

    assert response is not None
    assert "2499 MAD | jumia | 88/100" in response.message
    assert "without favoring" not in response.message.lower()
    assert "best balance" not in response.message.lower()
    assert "start with option" not in response.message.lower()


def test_materialize_llm_response_supports_neutral_darija_sections() -> None:
    event = make_ranked()
    event = DecisionRanked(
        request_id=event.request_id,
        user_id=event.user_id,
        channel=event.channel,
        user_text="Bghit Samsung phone b 3000 dh",
        query=event.query,
        products=event.products,
    )
    message = materialize_llm_response(
        event,
        (
            "INTRO: Hahuma 2 khityarat li lqit lik f Samsung.\n"
            "PRODUCT_HEADER: Tafasil dyal kol khityar:\n"
            "CLOSING: Tartib dyal l-lista kay7seb taman w thiqa. "
            "Qra l-ma3lomat w khod l-karar li 3jbek."
        ),
        fallback_message="fallback",
    )

    assert "Hahuma 2 khityarat" in message
    assert "Tafasil dyal kol khityar" in message
    assert "Taman: 2499 MAD" in message
    assert "Lien: https://example.com/jumia-a15" in message
    assert "l-ahsen" not in message.lower()
    assert "verify" not in message.lower()


def test_materialize_rejects_raw_llm_hallucination_without_products() -> None:
    from agents.agent_generator.tools.darija_copy import build_darija_no_results_reply

    event = DecisionRanked(
        request_id="req_empty",
        user_id="telegram_123",
        channel=Channel.TELEGRAM,
        user_text="bghit Samsung phone b 4000 dh",
        query=ProductQuery(product="phone", brand="Samsung", budget=4000),
        products=[],
    )
    fallback = build_darija_no_results_reply(event)
    message = materialize_llm_response(
        event,
        (
            "Salam! Chno bghiti n9leb lik 3lih? 3tini chno bghiti, ch7al l-mizaniya dyalek. "
            "JAWEB_1: Kayna: Jumia, Avito, Mafiawaystore Khityarat: Samsung Galaxy A13, "
            "Samsung Galaxy A12, Samsung Galaxy M12"
        ),
        fallback_message=fallback,
    )

    assert "JAWEB" not in message
    assert "Galaxy A13" not in message
    assert "Ma lqit" in message
    assert "4000" in message


def test_materialize_llm_response_supports_general_reply_without_products() -> None:
    event = DecisionRanked(
        request_id="req_hi",
        user_id="telegram_123",
        channel=Channel.WHATSAPP,
        user_text="Salam",
        products=[],
    )

    message = materialize_llm_response(
        event,
        "GENERAL_REPLY: Salam! Chno bghiti n9leb lik 3lih? 3tini chno bghiti w ch7al l-mizaniya dyalek.",
        fallback_message="fallback",
    )

    assert message.startswith("Salam!")
    assert "mizaniya" in message


def test_agent_generator_falls_back_when_llm_returns_unusable_unlabelled_text() -> None:
    producer = FakeProducer()
    generator = make_generator(producer=producer, llm_client=FakeLlmClient('A nice Samsung option.'))

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


def test_materialize_llm_response_rejects_repetitive_closing() -> None:
    event = make_ranked()
    event = DecisionRanked(
        request_id=event.request_id,
        user_id=event.user_id,
        channel=event.channel,
        user_text="Bghit Samsung phone b 3000 dh",
        query=event.query,
        products=event.products,
    )
    message = materialize_llm_response(
        event,
        (
            "INTRO: Bghit, ghadi 3 options ghadi fiha Samsung.\n"
            "CLOSING: Lihya Samsung Galaxy A15 128GB khairi, ghadi score ghadi qawi. "
            "Raktibhomhomhomhomhomhomhomhomhomhomhomhomhomhomhomhomhomhomhomhomhomhom"
        ),
        fallback_message="fallback",
    )

    assert "homhomhom" not in message
    assert "l-ahsen" not in message.lower()
    assert "karar" in message.lower() or "khtiar" in message.lower() or "khtar" in message.lower()
    assert len(message) < 1200


def test_build_darija_response_is_neutral_and_localized() -> None:
    from agents.agent_generator.tools.darija_copy import build_darija_response

    event = make_ranked()
    event = DecisionRanked(
        request_id=event.request_id,
        user_id=event.user_id,
        channel=event.channel,
        user_text="Bghit Samsung phone b 3000 dh",
        query=event.query,
        products=event.products,
    )
    message = build_darija_response(event)

    assert message.startswith("Hahuma") or message.startswith("L9it") or message.startswith("3la")
    assert "Taman:" in message
    assert "Lien:" in message
    assert "l-ahsen" not in message.lower()
    assert "verify" not in message.lower()
    assert "bla tafdil" not in message.lower()
    assert "karar" in message.lower() or "khtiar" in message.lower() or "khtar" in message.lower()


def test_materialize_rejects_mixed_language_darija_closing() -> None:
    event = make_ranked()
    event = DecisionRanked(
        request_id=event.request_id,
        user_id=event.user_id,
        channel=event.channel,
        user_text="Bghit Samsung phone b 3000 dh",
        query=event.query,
        products=event.products,
    )
    message = materialize_llm_response(
        event,
        (
            "INTRO: L9it lik 3 khityarat mzyanin.\n"
            "CLOSING: Best choice is option 1, verify seller before buying."
        ),
        fallback_message="fallback",
    )

    assert "karar" in message.lower() or "khtiar" in message.lower() or "khtar" in message.lower()
    assert "verify seller" not in message.lower()
    assert "best choice" not in message.lower()


def test_darija_closing_varies_with_user_text() -> None:
    from agents.agent_generator.tools.darija_copy import darija_closing

    closing_a = darija_closing(seed="Bghit Samsung phone b 3000 dh")
    closing_b = darija_closing(seed="Kan9leb 3la tilifun Samsung")
    assert closing_a != closing_b


def test_stale_darija_closing_rejects_prompt_echo() -> None:
    from agents.agent_generator.tools.darija_copy import DARIJA_CLOSING_VARIANTS, is_stale_darija_closing
    from agents.agent_generator.tools.text_safety import mentions_neutrality_disclaimer

    assert is_stale_darija_closing(
        "Rattabt l-lista 3la taman, thiqa, w l-wjoud bla tafdil. Chouf l-ma3lomat w dir l-karar li 3jbek."
    )
    assert not is_stale_darija_closing(DARIJA_CLOSING_VARIANTS[1])
    assert mentions_neutrality_disclaimer(
        "Tartib dyal l-lista kay7seb taman w thiqa bla tafdil. Khtar li bghiti mn ba3d ma t-qra."
    )


def test_materialize_rejects_neutrality_disclaimer_closing() -> None:
    event = make_ranked()
    message = materialize_llm_response(
        event,
        (
            "INTRO: Here are 2 options from your search.\n"
            "CLOSING: These options are listed without favoring any option. Review and decide."
        ),
        fallback_message="fallback",
    )

    assert "without favoring" not in message.lower()
    assert "2499 MAD" in message


def test_localized_closing_varies_with_user_text() -> None:
    from agents.agent_generator.tools.response_copy import localized_closing

    closing_en_a = localized_closing("en", seed="I need a Samsung phone under 3000 MAD in Casablanca")
    closing_en_b = localized_closing("en", seed="Looking for gaming laptop under 5000 dirhams")
    closing_fr_a = localized_closing("fr", seed="Je cherche un telephone Samsung pas cher")
    closing_fr_b = localized_closing("fr", seed="Je veux un laptop portable pour etudier")
    assert closing_en_a != closing_en_b or closing_fr_a != closing_fr_b
    assert "sans favoriser" not in closing_fr_a.lower()
    assert "without favoring" not in closing_en_a.lower()


def test_sanitize_llm_prose_strips_repetition() -> None:
    from agents.agent_generator.tools.text_safety import sanitize_llm_prose

    cleaned = sanitize_llm_prose("Good answer. Raktibhomhomhomhomhomhomhomhom")
    assert "homhom" not in cleaned
    assert cleaned.startswith("Good answer.")


def test_llm_generator_script_sample_ranked_has_required_facts() -> None:
    event = build_sample_ranked()

    assert event.request_id == "req_llm_test"
    assert len(event.products) == 3
    assert event.products[0].title == "Samsung Galaxy A15 128GB"
    assert str(event.products[0].url) == "https://example.com/jumia-a15"
