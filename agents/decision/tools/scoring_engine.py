"""Decision scoring based on the architecture report's 100-point system."""

from __future__ import annotations

import re

from shared.events.schemas import (
    Availability,
    ProductQuery,
    RankedProduct,
    RawProduct,
    ScoreBreakdown,
)

TRUSTED_SOURCES = {
    "jumia": 30,
    "official": 30,
    "avito": 20,
    "facebook": 12,
    "instagram": 12,
}


def rank_products(products: list[RawProduct], query: ProductQuery) -> list[RankedProduct]:
    unique_products = deduplicate_products(products)
    ranked = [score_product(product, query) for product in unique_products]
    return sorted(ranked, key=lambda product: product.score, reverse=True)


def deduplicate_products(products: list[RawProduct]) -> list[RawProduct]:
    seen: set[str] = set()
    unique: list[RawProduct] = []

    for product in products:
        key = _dedup_key(product)
        if key in seen:
            continue
        seen.add(key)
        unique.append(product)

    return unique


def score_product(product: RawProduct, query: ProductQuery) -> RankedProduct:
    breakdown = ScoreBreakdown(
        price=_price_score(product, query),
        trust=_trust_score(product),
        quality=_quality_score(product, query),
        availability=_availability_score(product),
    )

    return RankedProduct(
        title=product.title,
        price=product.price,
        currency=product.currency,
        source=product.source,
        url=product.url,
        availability=product.availability,
        seller=product.seller,
        rating=product.rating,
        score=breakdown.total,
        score_breakdown=breakdown,
    )


def _price_score(product: RawProduct, query: ProductQuery) -> int:
    if query.budget is None:
        return 30
    if product.price <= query.budget:
        ratio = product.price / query.budget if query.budget else 1
        return max(25, round(40 - (ratio * 10)))
    over_budget_ratio = (product.price - query.budget) / query.budget
    return max(0, round(25 - (over_budget_ratio * 50)))


def _trust_score(product: RawProduct) -> int:
    source = product.source.lower()
    seller = (product.seller or "").lower()

    for trusted_source, score in TRUSTED_SOURCES.items():
        if trusted_source in source or trusted_source in seller:
            return score
    return 15


def _quality_score(product: RawProduct, query: ProductQuery) -> int:
    score = 10
    title = product.title.lower()

    if query.brand and query.brand.lower() in title:
        score += 4
    if query.product and query.product.lower() in title:
        score += 2
    if product.rating is not None:
        score += round((product.rating / 5) * 4)

    return min(score, 20)


def _availability_score(product: RawProduct) -> int:
    if product.availability == Availability.IN_STOCK:
        return 10
    if product.availability == Availability.UNKNOWN:
        return 5
    return 0


def _dedup_key(product: RawProduct) -> str:
    normalized_title = re.sub(r"[^a-z0-9]+", "", product.title.lower())
    return f"{product.source.lower()}:{normalized_title}:{round(product.price)}"
