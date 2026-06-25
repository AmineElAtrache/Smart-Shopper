"""Product deduplication helpers for decision ranking."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from shared.events.schemas import RawProduct


def deduplicate_products(products: list[RawProduct], *, similarity_threshold: float = 0.92) -> list[RawProduct]:
    unique: list[RawProduct] = []
    seen_keys: set[str] = set()

    for product in products:
        exact_key = _exact_key(product)
        if exact_key in seen_keys:
            continue
        if any(_looks_like_same_listing(product, existing, similarity_threshold) for existing in unique):
            continue
        seen_keys.add(exact_key)
        unique.append(product)

    return unique


def _exact_key(product: RawProduct) -> str:
    return f"{product.source.lower()}:{_normalize(product.title)}:{round(product.price)}"


def _looks_like_same_listing(
    product: RawProduct,
    existing: RawProduct,
    similarity_threshold: float,
) -> bool:
    if product.source.lower() != existing.source.lower():
        return False
    if abs(product.price - existing.price) > max(10, existing.price * 0.03):
        return False
    similarity = SequenceMatcher(None, _normalize(product.title), _normalize(existing.title)).ratio()
    return similarity >= similarity_threshold


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())
