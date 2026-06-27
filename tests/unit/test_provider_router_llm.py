"""Tests for LLM-backed provider category routing."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agents.orchestrator.agent import OrchestratorAgent, _entity_hints
from agents.orchestrator.tools.provider_router import route_sites
from agents.orchestrator.tools.provider_router_llm import (
    ProviderRouterLlmClient,
    build_routing_user_prompt,
    parse_category_response,
)
from agents.orchestrator.tools.task_router import build_product_query
from shared.config import Settings
from shared.events.schemas import EntityType, ExtractedEntity, InboundMessage


def test_parse_category_response_accepts_json() -> None:
    assert parse_category_response('{"category":"furniture"}') == "furniture"


def test_parse_category_response_accepts_markdown_json() -> None:
    assert parse_category_response('```json\n{"category":"phone"}\n```') == "phone"


def test_parse_category_response_rejects_unknown_category() -> None:
    assert parse_category_response('{"category":"spaceship"}') is None


def test_build_routing_user_prompt_includes_ner_hints() -> None:
    prompt = build_routing_user_prompt(
        "bghit table f rabat b 400dh",
        product="table",
        city="rabat",
        budget=400,
    )

    assert "bghit table f rabat b 400dh" in prompt
    assert "product=table" in prompt
    assert "city=rabat" in prompt
    assert "budget=400 MAD" in prompt


def test_route_sites_uses_explicit_category_over_product() -> None:
    sites = route_sites("tablet", category="furniture")

    assert sites == ["ikea", "avito", "jumia"]


def test_provider_router_llm_disabled_when_template_provider() -> None:
    settings = Settings(_env_file=None, llm_provider="template", scrape_route_use_llm=True)
    client = ProviderRouterLlmClient(settings)

    assert client.llm_routing_enabled() is False


@pytest.mark.asyncio
async def test_provider_router_llm_classifies_category(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCRAPE_ROUTE_USE_LLM", "true")
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    settings = Settings(_env_file=None)
    client = ProviderRouterLlmClient(settings)
    assert client.llm_routing_enabled() is True

    with patch.object(
        client,
        "_call_openai_compatible",
        new=AsyncMock(return_value='{"category":"furniture"}'),
    ) as mock_call:
        category = await client.classify_category(
            "bghit table f rabat b 400dh",
            product="table",
            city="rabat",
            budget=400,
        )

    assert category == "furniture"
    mock_call.assert_awaited_once()


@pytest.mark.asyncio
async def test_provider_router_llm_returns_none_on_invalid_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCRAPE_ROUTE_USE_LLM", "true")
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    settings = Settings(_env_file=None)
    client = ProviderRouterLlmClient(settings)

    with patch.object(
        client,
        "_call_openai_compatible",
        new=AsyncMock(return_value="I think this is furniture."),
    ):
        category = await client.classify_category("bghit table f rabat")

    assert category is None


@pytest.mark.asyncio
async def test_orchestrator_uses_llm_category_for_routing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCRAPE_ROUTE_USE_LLM", "true")
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    settings = Settings(_env_file=None)

    class FakeNerClient:
        async def extract(self, text, locale_hint=None):
            return [
                ExtractedEntity(type=EntityType.PRODUCT, value="tablet", confidence=0.9),
                ExtractedEntity(type=EntityType.CITY, value="rabat", confidence=0.9),
                ExtractedEntity(type=EntityType.BUDGET, value="400", confidence=0.9),
            ]

    router_llm = ProviderRouterLlmClient(settings)
    agent = OrchestratorAgent(ner_client=FakeNerClient(), router_llm=router_llm, settings=settings)
    message = InboundMessage(
        request_id="req_table",
        user_id="u1",
        text="bghit table f rabat b 400dh",
    )

    with patch.object(
        router_llm,
        "classify_category",
        new=AsyncMock(return_value="furniture"),
    ):
        _extracted, task = await agent.handle_inbound(message)

    assert task.query.sites == ["ikea", "avito", "jumia"]


def test_entity_hints_collects_budget_currency() -> None:
    hints = _entity_hints(
        [
            ExtractedEntity(
                type=EntityType.BUDGET,
                value="400",
                confidence=0.9,
                attributes={"currency": "MAD"},
            ),
            ExtractedEntity(type=EntityType.PRODUCT, value="table", confidence=0.9),
        ]
    )

    assert hints["product"] == "table"
    assert hints["budget"] == 400.0
    assert hints["currency"] == "MAD"


def test_build_product_query_accepts_explicit_category() -> None:
    query = build_product_query(
        [ExtractedEntity(type=EntityType.PRODUCT, value="tablet", confidence=0.9)],
        category="furniture",
    )

    assert query.sites == ["ikea", "avito", "jumia"]
