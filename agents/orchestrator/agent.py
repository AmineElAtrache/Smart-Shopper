"""Orchestrator Agent for inbound shopping requests."""

from __future__ import annotations

from agents.orchestrator.tools.entity_enrichment_llm import (
    EntityEnrichmentLlmClient,
    merge_enriched_entities,
)
from agents.orchestrator.tools.ner_client import NerClient
from agents.orchestrator.tools.provider_router_llm import ProviderRouterLlmClient
from agents.orchestrator.tools.task_router import build_scrape_task
from shared.config import Settings, get_settings
from shared.events.schemas import EntityType, ExtractedEntity, InboundMessage, NerExtracted, ScrapeTaskAssigned


class OrchestratorAgent:
    def __init__(
        self,
        ner_client: NerClient | None = None,
        router_llm: ProviderRouterLlmClient | None = None,
        enrichment_llm: EntityEnrichmentLlmClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._ner_client = ner_client or NerClient()
        self._router_llm = router_llm or ProviderRouterLlmClient(self._settings)
        self._enrichment_llm = enrichment_llm or EntityEnrichmentLlmClient(self._settings)

    async def handle_inbound(self, message: InboundMessage) -> tuple[NerExtracted, ScrapeTaskAssigned]:
        entities = await self._ner_client.extract(message.text, locale_hint=message.locale_hint)
        hints = _entity_hints(entities)
        enriched = await self._enrichment_llm.enrich(
            message.text,
            product=_hint_str(hints.get("product")),
            brand=_hint_str(hints.get("brand")),
            city=_hint_str(hints.get("city")),
            color=_hint_str(hints.get("color")),
            budget=_hint_float(hints.get("budget")),
        )
        if enriched:
            print(
                f"[orchestrator] entity enrichment request_id={message.request_id} "
                f"city={enriched.get('city')} color={enriched.get('color')}"
            )
        entities = merge_enriched_entities(entities, enriched)
        extracted = NerExtracted(
            request_id=message.request_id,
            user_id=message.user_id,
            channel=message.channel,
            text=message.text,
            entities=entities,
        )
        category = await self._resolve_routing_category(message.text, entities, message.request_id)
        task = build_scrape_task(message, entities, category=category)
        return extracted, task

    async def _resolve_routing_category(
        self,
        user_text: str,
        entities: list[ExtractedEntity],
        request_id: str,
    ) -> str | None:
        hints = _entity_hints(entities)
        category = await self._router_llm.classify_category(
            user_text,
            product=_hint_str(hints.get("product")),
            brand=_hint_str(hints.get("brand")),
            city=_hint_str(hints.get("city")),
            budget=_hint_float(hints.get("budget")),
            currency=_hint_str(hints.get("currency")) or "MAD",
        )
        if category is not None:
            print(f"[orchestrator] LLM provider route category={category} request_id={request_id}")
            return category

        if self._router_llm.llm_routing_enabled():
            static_category = self._router_llm.static_category(_hint_str(hints.get("product")))
            print(
                f"[orchestrator] LLM provider route fallback category={static_category} "
                f"request_id={request_id}"
            )
        return None


def _entity_hints(entities: list[ExtractedEntity]) -> dict[str, str | float]:
    hints: dict[str, str | float] = {}
    currency = "MAD"
    for entity in entities:
        if entity.type == EntityType.PRODUCT:
            hints["product"] = entity.value
        elif entity.type == EntityType.BRAND:
            hints["brand"] = entity.value
        elif entity.type == EntityType.CITY:
            hints["city"] = entity.value
        elif entity.type == EntityType.COLOR:
            hints["color"] = entity.value
        elif entity.type in {EntityType.PRICE, EntityType.BUDGET}:
            hints["budget"] = float(entity.value)
            currency = entity.attributes.get("currency", currency)
        elif entity.type == EntityType.CURRENCY:
            currency = entity.value
    hints["currency"] = currency
    return hints


def _hint_str(value: str | float | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _hint_float(value: str | float | None) -> float | None:
    if value is None:
        return None
    return float(value)
