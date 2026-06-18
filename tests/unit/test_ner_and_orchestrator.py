import pytest

from agents.orchestrator.agent import OrchestratorAgent
from models.ner.serve import extract_entities
from shared.events.schemas import InboundMessage


def test_rule_based_ner_extracts_brand_product_and_budget() -> None:
    entities = extract_entities("Bghit Samsung phone b 3000 dh")
    by_type = {entity.type: entity for entity in entities}

    assert by_type["brand"].value == "Samsung"
    assert by_type["product"].value == "phone"
    assert by_type["budget"].value == "3000.0"
    assert by_type["budget"].attributes["currency"] == "MAD"


@pytest.mark.asyncio
async def test_orchestrator_builds_scrape_task_from_inbound_message() -> None:
    message = InboundMessage(
        request_id="req_001",
        user_id="telegram_123",
        text="Find me a Samsung phone under 3000 MAD",
    )

    extracted, task = await OrchestratorAgent().handle_inbound(message)

    assert extracted.request_id == "req_001"
    assert task.request_id == "req_001"
    assert task.query.brand == "Samsung"
    assert task.query.product == "phone"
    assert task.query.budget == 3000
    assert task.query.sites == ["jumia", "avito"]
