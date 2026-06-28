"""Build scraping tasks from extracted entities."""

from __future__ import annotations

import os

from agents.orchestrator.tools.provider_router import CATEGORY_SITES, classify_product
from shared.events.schemas import (
    EntityType,
    ExtractedEntity,
    InboundMessage,
    ProductQuery,
    ScrapeTaskAssigned,
)

def _provider_routing_enabled() -> bool:
    return os.getenv("SCRAPE_ROUTE_PROVIDERS", "true").lower() in {"1", "true", "yes"}


def build_product_query(
    entities: list[ExtractedEntity],
    *,
    category: str | None = None,
    sites: list[str] | None = None,
) -> ProductQuery:
    product: str | None = None
    brand: str | None = None
    budget: float | None = None
    currency = "MAD"
    city: str | None = None
    color: str | None = None
    quality: str | None = None

    for entity in entities:
        if entity.type == EntityType.PRODUCT:
            product = entity.value
        elif entity.type == EntityType.BRAND:
            brand = entity.value
        elif entity.type in {EntityType.PRICE, EntityType.BUDGET}:
            budget = float(entity.value)
            currency = entity.attributes.get("currency", currency)
        elif entity.type == EntityType.CURRENCY:
            currency = entity.value
        elif entity.type == EntityType.CITY:
            city = entity.value
        elif entity.type == EntityType.COLOR:
            color = entity.value
        elif entity.type == EntityType.QUALITY:
            quality = entity.value

    if sites is None:
        from agents.orchestrator.tools.provider_router import route_sites

        resolved_category = category if category in CATEGORY_SITES else classify_product(product)
        sites = route_sites(
            product,
            category=resolved_category,
            city=city,
            color=color,
            route_enabled=_provider_routing_enabled(),
        )

    return ProductQuery(
        product=product,
        brand=brand,
        budget=budget,
        currency=currency,
        city=city,
        color=color,
        quality=quality,
        sites=sites,
    )


def build_scrape_task(
    message: InboundMessage,
    entities: list[ExtractedEntity],
    *,
    category: str | None = None,
    sites: list[str] | None = None,
) -> ScrapeTaskAssigned:
    return ScrapeTaskAssigned(
        request_id=message.request_id,
        user_id=message.user_id,
        channel=message.channel,
        query=build_product_query(entities, category=category, sites=sites),
        user_text=message.text.strip(),
    )
