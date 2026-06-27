import asyncio

import pytest

from agents.orchestrator.agent import OrchestratorAgent
from agents.orchestrator.tools.provider_router import classify_product, route_sites
from agents.orchestrator.tools.task_router import build_product_query
from models.ner.serve import _preprocess_text, extract_entities
from models.ner.product_vocabulary import (
    city_aliases,
    load_vocabulary,
    normalize_text as normalize_vocabulary_text,
)
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
    assert by_type["product"].value in {"golf", "car"}
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
    if "product" in by_type:
        assert by_type["product"].value in {"phone", "iphone"}
    assert by_type["city"].value == "fes"
    assert by_type["budget"].value == "4500.0"


def test_ner_filters_weak_false_brand_from_darija_context() -> None:
    entities = extract_entities("kan9lebe 3la chi pc ykone nadi mayfotch 3000ddh")
    by_type = {entity.type: entity for entity in entities}

    assert "brand" not in by_type
    assert by_type["product"].value in {"laptop", "pc"}
    assert by_type["budget"].value == "3000.0"
    assert by_type["budget"].attributes["currency"] == "MAD"


def test_ner_does_not_parse_digits_inside_darija_words() -> None:
    entities = extract_entities("kan9lebe 3la chi telaja fes tkone jdida we maghalyach")
    by_type = {entity.type: entity for entity in entities}

    assert by_type["product"].value in {"fridge", "refrigerator", "refrigera"}
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
        "ultrapc",
        "electroplanet",
        "biougnach",
    ]

def test_product_vocabulary_resource_is_loaded() -> None:
    assert len(load_vocabulary()) >= 700


def test_product_vocabulary_normalizes_multilingual_typos() -> None:
    normalized = normalize_vocabulary_text("bghit samsong galaxi a15 smarfone kehla")

    assert "samsung" in normalized
    assert "galaxy a15" in normalized
    assert "phone" in normalized
    assert "black" in normalized


def test_city_aliases_are_loaded_from_vocabulary() -> None:
    aliases = city_aliases()

    assert len(aliases) >= 50
    assert aliases["casa"] == "casablanca"
    assert aliases["mohammedia"] == "mohammedia"
    assert aliases["tanja"] == "tanger"
    assert aliases["el_jadida"] == "el_jadida"


def test_ner_extracts_fridge_instead_of_darija_preposition_f() -> None:
    entities = extract_entities("I want to buy a fridge for 8000 DH")
    by_type = {entity.type: entity for entity in entities}

    assert by_type["product"].value in {"fridge", "refrigerator"}
    assert by_type["budget"].value == "8000.0"


def test_ner_detects_vocabulary_synced_cities() -> None:
    entities = extract_entities("bghit appartement f mohammedia b 400000dh")
    by_type = {entity.type: entity for entity in entities}

    assert by_type["city"].value == "mohammedia"
    assert by_type["budget"].value == "400000.0"


def test_product_vocabulary_covers_provider_expansion() -> None:
    normalized = normalize_vocabulary_text("bghit cream loreal f dar el beida w chaussures running nike")

    assert "cream" in normalized
    assert "loreal" in normalized
    assert "casablanca" in normalized
    assert "running_shoes" in normalized
    assert "Nike".lower() in normalized


def test_ner_keeps_furniture_table_distinct_from_tablet() -> None:
    assert "table" in _preprocess_text("bghit table f rabat b 400dh")
    assert "tablet" not in _preprocess_text("bghit table f rabat b 400dh")

    entities = extract_entities("bghit table f rabat b 400dh")
    by_type = {entity.type: entity for entity in entities}

    assert by_type["product"].value == "table"
    assert by_type["city"].value == "rabat"
    assert by_type["budget"].value == "400.0"
    assert classify_product(by_type["product"].value) == "furniture"
    assert "ikea" in route_sites(by_type["product"].value)


def test_ner_extracts_tablet_for_explicit_tablet_query() -> None:
    entities = extract_entities("bghit tablet f rabat b 4000dh")
    by_type = {entity.type: entity for entity in entities}

    assert by_type["product"].value == "tablet"
    assert classify_product(by_type["product"].value) == "laptop"


def test_ner_uses_vocabulary_without_model_predictions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("models.ner.serve._extract_with_model", lambda text: [])

    entities = extract_entities("bghit samsong galaxi a15 kehla b 1500dh")
    by_type = {entity.type: entity for entity in entities}

    assert by_type["brand"].value == "Samsung"
    assert by_type["product"].value in {"Galaxy A15", "galaxy a15"}
    assert by_type["color"].value == "black"
    assert by_type["budget"].value == "1500.0"
