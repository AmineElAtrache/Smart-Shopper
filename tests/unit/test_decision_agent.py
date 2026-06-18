from agents.decision.agent import DecisionAgent
from shared.events.schemas import Availability, ProductQuery, RawProduct


def test_decision_agent_ranks_best_product_first() -> None:
    query = ProductQuery(product="phone", brand="Samsung", budget=3000)
    products = [
        RawProduct(
            request_id="req_001",
            source="avito",
            title="Samsung Galaxy A15",
            price=3300,
            url="https://example.com/avito-a15",
            availability=Availability.UNKNOWN,
            seller="Private seller",
            rating=3.5,
        ),
        RawProduct(
            request_id="req_001",
            source="jumia",
            title="Samsung Galaxy A15 128GB",
            price=2499,
            url="https://example.com/jumia-a15",
            availability=Availability.IN_STOCK,
            seller="Jumia official",
            rating=4.5,
        ),
    ]

    ranked = DecisionAgent().rank(
        request_id="req_001",
        user_id="telegram_123",
        channel="telegram",
        query=query,
        products=products,
    )

    assert ranked.products[0].source == "jumia"
    assert ranked.products[0].score > ranked.products[1].score
    assert ranked.products[0].score_breakdown.price <= 40
    assert ranked.products[0].score_breakdown.trust <= 30
