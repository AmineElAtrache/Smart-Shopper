from agents.agent_generator.agent import build_outbound_response, build_response_message
from agents.webscraping.agent import build_mock_products
from gateway.telegram_proxy import build_inbound_message, chat_id_from_user_id
from shared.events.schemas import (
    Availability,
    Channel,
    DecisionRanked,
    ProductQuery,
    RankedProduct,
    ScoreBreakdown,
    ScrapeTaskAssigned,
)


def test_telegram_text_becomes_inbound_message() -> None:
    event = build_inbound_message(chat_id=123, text=" Samsung phone under 3000 MAD ")

    assert event.user_id == "telegram_123"
    assert event.channel == Channel.TELEGRAM
    assert event.text == "Samsung phone under 3000 MAD"
    assert chat_id_from_user_id(event.user_id) == 123


def test_mock_scraper_generates_rankable_products() -> None:
    task = ScrapeTaskAssigned(
        request_id="req_001",
        user_id="telegram_123",
        channel=Channel.TELEGRAM,
        query=ProductQuery(product="phone", brand="Samsung", budget=3000),
    )

    products = build_mock_products(task)

    assert len(products) >= 3
    assert {product.request_id for product in products} == {"req_001"}
    assert {product.user_id for product in products} == {"telegram_123"}
    assert {product.channel for product in products} == {"telegram"}
    assert all(product.query == task.query for product in products)
    assert {"jumia", "avito"}.issubset({product.source for product in products})
    assert any(
        product.price <= 3000 and product.availability == Availability.IN_STOCK
        for product in products
    )
    assert any("Samsung" in product.title and "phone" in product.title for product in products)


def test_agent_generator_builds_outbound_response_with_product_details() -> None:
    ranked = DecisionRanked(
        request_id="req_001",
        user_id="telegram_123",
        channel=Channel.TELEGRAM,
        products=[
            RankedProduct(
                title="Samsung Galaxy A15 128GB",
                price=2499,
                source="jumia",
                url="https://example.com/jumia-a15",
                availability=Availability.IN_STOCK,
                score=88,
                score_breakdown=ScoreBreakdown(
                    price=36,
                    trust=27,
                    quality=17,
                    availability=8,
                ),
            )
        ],
    )

    response = build_outbound_response(ranked)

    assert response.request_id == "req_001"
    assert response.user_id == "telegram_123"
    assert response.channel == "telegram"
    assert "Samsung Galaxy A15 128GB" in response.message
    assert "2499 MAD" in response.message
    assert "jumia" in response.message
    assert "88/100" in response.message
    assert "https://example.com/jumia-a15" in response.message


def test_agent_generator_empty_products_fallback() -> None:
    message = build_response_message([])

    assert "could not find" in message
    assert "budget" in message
