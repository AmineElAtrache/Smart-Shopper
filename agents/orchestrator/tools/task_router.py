"""Build scraping tasks from extracted entities."""

from __future__ import annotations

from shared.events.schemas import (
    EntityType,
    ExtractedEntity,
    InboundMessage,
    ProductQuery,
    ScrapeTaskAssigned,
)

DEFAULT_SITES = ["jumia", "avito"]


def build_product_query(entities: list[ExtractedEntity]) -> ProductQuery:
    product: str | None = None
    brand: str | None = None
    budget: float | None = None
    currency = "MAD"
    quality: str | None = None
    sites = list(DEFAULT_SITES)

    for entity in entities:
        if entity.type == EntityType.PRODUCT:
            product = entity.value
        elif entity.type == EntityType.BRAND:
            brand = entity.value
        elif entity.type == EntityType.BUDGET:
            budget = float(entity.value)
            currency = entity.attributes.get("currency", currency)
        elif entity.type == EntityType.CURRENCY:
            currency = entity.value
        elif entity.type == EntityType.QUALITY:
            quality = entity.value

    return ProductQuery(
        product=product,
        brand=brand,
        budget=budget,
        currency=currency,
        quality=quality,
        sites=sites,
    )


def build_scrape_task(message: InboundMessage, entities: list[ExtractedEntity]) -> ScrapeTaskAssigned:
    return ScrapeTaskAssigned(
        request_id=message.request_id,
        user_id=message.user_id,
        channel=message.channel,
        query=build_product_query(entities),
    )
