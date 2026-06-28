"""Tests for LLM-backed city/color entity enrichment."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agents.orchestrator.tools.entity_enrichment_llm import (
    EntityEnrichmentLlmClient,
    merge_enriched_entities,
    parse_enrichment_response,
)
from shared.config import Settings
from shared.events.schemas import EntityType, ExtractedEntity


def test_parse_enrichment_response_normalizes_city_and_color() -> None:
    parsed = parse_enrichment_response('{"city":"casa","color":"noir"}')

    assert parsed["city"] == "casablanca"
    assert parsed["color"] == "black"


def test_merge_enriched_entities_adds_missing_city_and_color() -> None:
    entities = [
        ExtractedEntity(type=EntityType.PRODUCT, value="phone", confidence=0.9),
    ]
    merged = merge_enriched_entities(entities, {"city": "rabat", "color": "black"})

    by_type = {entity.type: entity for entity in merged}
    assert by_type[EntityType.CITY].value == "rabat"
    assert by_type[EntityType.COLOR].value == "black"
    assert by_type[EntityType.CITY].attributes["source"] == "entity_enrichment_llm"


def test_merge_enriched_entities_does_not_override_existing() -> None:
    entities = [
        ExtractedEntity(type=EntityType.CITY, value="fes", confidence=0.9),
    ]
    merged = merge_enriched_entities(entities, {"city": "rabat", "color": "black"})

    by_type = {entity.type: entity for entity in merged}
    assert by_type[EntityType.CITY].value == "fes"
    assert by_type[EntityType.COLOR].value == "black"


def test_entity_enrichment_disabled_by_default() -> None:
    settings = Settings(_env_file=None, scrape_enrich_entities_llm=False, llm_provider="groq", llm_api_key="key")
    client = EntityEnrichmentLlmClient(settings)

    assert client.enrichment_enabled() is False


@pytest.mark.asyncio
async def test_entity_enrichment_fills_missing_city(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCRAPE_ENRICH_ENTITIES_LLM", "true")
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    settings = Settings(_env_file=None)
    client = EntityEnrichmentLlmClient(settings)

    with patch.object(
        client,
        "_call_openai_compatible",
        new=AsyncMock(return_value='{"city":"rabat","color":null}'),
    ):
        enriched = await client.enrich(
            "bghit table f rabat b 400dh",
            product="table",
            city=None,
            color=None,
            budget=400,
        )

    assert enriched == {"city": "rabat"}
