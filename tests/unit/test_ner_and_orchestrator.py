import asyncio

import pytest

from agents.orchestrator.agent import OrchestratorAgent
from agents.orchestrator.tools.task_router import build_product_query
from models.ner.serve import extract_entities
from shared.events.schemas import EntityType, ExtractedEntity, InboundMessage


def test_ner_model_extracts_brand_product_and_budget() -> None:
    entities = extract_entities("Bghit Samsung phone b 3000 dh")
    by_type = {entity.type: entity for entity in entities}

    assert by_type["brand"].value == "Samsung"
    assert by_type["product"].value == "phone"
    assert by_type["price"].value == "3000.0"
    assert by_type["budget"].value == "3000.0"
    assert by_type["budget"].attributes["currency"] == "MAD"


def test_ner_enrichment_extracts_city_and_color() -> None:
    entities = extract_entities("Bghit Samsung phone black f Casablanca b 3000 dh")
    by_type = {entity.type: entity for entity in entities}

    assert by_type["city"].value == "casablanca"
    assert by_type["color"].value == "black"


def test_ner_enrichment_normalizes_darija_vehicle_query() -> None:
    entities = extract_entities("bghit tomobile golf kehla we ana 3endi hi 50000dh")
    by_type = {entity.type: entity for entity in entities}

    assert by_type["brand"].value == "Volkswagen"
    assert by_type["product"].value == "golf"
    assert by_type["color"].value == "black"
    assert by_type["budget"].value == "50000.0"
    assert by_type["budget"].attributes["currency"] == "MAD"


def test_ner_enrichment_detects_model_name_after_brand() -> None:
    entities = extract_entities("bghit hp omen f fes b 6000dh")
    by_type = {entity.type: entity for entity in entities}

    assert by_type["brand"].value == "HP"
    assert by_type["product"].value == "omen"
    assert by_type["city"].value == "fes"
    assert by_type["budget"].value == "6000.0"


def test_ner_preprocesses_misspellings_before_model() -> None:
    entities = extract_entities("bghit samsng phne black f casaa b 3000dh")
    by_type = {entity.type: entity for entity in entities}

    assert by_type["brand"].value == "Samsung"
    assert by_type["product"].value == "phone"
    assert by_type["city"].value == "casablanca"
    assert by_type["color"].value == "black"
    assert by_type["budget"].value == "3000.0"


def test_ner_preprocesses_accents_and_darija_aliases() -> None:
    entities = extract_entities("bghit iphon f f\u00e8s b 4500dhs")
    by_type = {entity.type: entity for entity in entities}

    assert by_type["brand"].value == "Apple"
    assert by_type["product"].value == "phone"
    assert by_type["city"].value == "fes"
    assert by_type["budget"].value == "4500.0"


def test_ner_filters_weak_false_brand_from_darija_context() -> None:
    entities = extract_entities("kan9lebe 3la chi pc ykone nadi mayfotch 3000ddh")
    by_type = {entity.type: entity for entity in entities}

    assert "brand" not in by_type
    assert by_type["product"].value == "laptop"
    assert by_type["budget"].value == "3000.0"
    assert by_type["budget"].attributes["currency"] == "MAD"


def test_ner_does_not_parse_digits_inside_darija_words() -> None:
    entities = extract_entities("kan9lebe 3la chi telaja fes tkone jdida we maghalyach")
    by_type = {entity.type: entity for entity in entities}

    assert by_type["product"].value == "fridge"
    assert by_type["city"].value == "fes"
    assert by_type["quality"].value == "new"
    assert "price" not in by_type
    assert "budget" not in by_type
    assert "currency" not in by_type


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
