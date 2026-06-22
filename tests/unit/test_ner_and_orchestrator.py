import asyncio

from agents.orchestrator.agent import OrchestratorAgent
from agents.orchestrator.tools.task_router import build_product_query
from models.ner.serve import extract_entities
from shared.events.schemas import EntityType, ExtractedEntity, InboundMessage


def test_rule_based_ner_extracts_brand_product_and_budget() -> None:
    entities = extract_entities("Bghit Samsung phone b 3000 dh")
    by_type = {entity.type: entity for entity in entities}

    assert by_type["brand"].value == "Samsung"
    assert by_type["product"].value == "phone"
    assert by_type["price"].value == "3000.0"
    assert by_type["budget"].value == "3000.0"
    assert by_type["budget"].attributes["currency"] == "MAD"


def test_rule_based_ner_extracts_city_and_color() -> None:
    entities = extract_entities("Bghit Samsung phone black f Casablanca b 3000 dh")
    by_type = {entity.type: entity for entity in entities}

    assert by_type["city"].value == "casablanca"
    assert by_type["color"].value == "black"


def test_task_router_maps_price_city_and_color_entities() -> None:
    query = build_product_query(
        [
            ExtractedEntity(type=EntityType.PRODUCT, value="phone", confidence=0.9),
            ExtractedEntity(type=EntityType.BRAND, value="Samsung", confidence=0.9),
            ExtractedEntity(
                type=EntityType.PRICE,
                value="3000",
                confidence=0.9,
                attributes={"currency": "MAD"},
            ),
            ExtractedEntity(type=EntityType.CITY, value="casablanca", confidence=0.8),
            ExtractedEntity(type=EntityType.COLOR, value="black", confidence=0.8),
        ]
    )

    assert query.product == "phone"
    assert query.brand == "Samsung"
    assert query.budget == 3000
    assert query.currency == "MAD"
    assert query.city == "casablanca"
    assert query.color == "black"


def test_orchestrator_builds_scrape_task_from_inbound_message() -> None:
    message = InboundMessage(
        request_id="req_001",
        user_id="telegram_123",
        text="Find me a Samsung phone under 3000 MAD",
    )

    extracted, task = asyncio.run(OrchestratorAgent().handle_inbound(message))

    assert extracted.request_id == "req_001"
    assert task.request_id == "req_001"
    assert task.query.brand == "Samsung"
    assert task.query.product == "phone"
    assert task.query.budget == 3000
    assert task.query.sites == [
        "jumia",
        "avito",
        "electrosalam",
        "mafiawaystore",
        "moteur",
        "mymarket",
        "ultrapc",
        "electroplanet",
        "defacto",
        "biougnach",
        "marjane",
        "decathlon",
        "mubawab",
        "ikea",
    ]
