"""Rule-based NER placeholder for Moroccan shopping queries.

The architecture expects XLM-RoBERTa later. This module gives the
Orchestrator a stable interface now, so the rest of the pipeline can be built.
"""

from __future__ import annotations

import re

from shared.events.schemas import EntityType, ExtractedEntity

BRANDS = {
    "samsung",
    "iphone",
    "apple",
    "xiaomi",
    "redmi",
    "oppo",
    "hp",
    "dell",
    "lenovo",
    "asus",
    "acer",
}

PRODUCT_KEYWORDS = {
    "phone": {"phone", "smartphone", "telephone", "téléphone", "tel", "iphone"},
    "laptop": {"laptop", "pc", "ordinateur", "portable", "pc portable"},
    "tablet": {"tablet", "tablette", "ipad"},
    "headphones": {"headphones", "casque", "ecouteurs", "écouteurs"},
}

BUDGET_PATTERN = re.compile(
    r"(?P<amount>\d+(?:[.,]\d+)?)\s*(?P<currency>mad|dh|dhs|dirham|dirhams|درهم)?",
    re.IGNORECASE,
)


def extract_entities(text: str, locale_hint: str | None = None) -> list[ExtractedEntity]:
    normalized = text.lower().strip()
    entities: list[ExtractedEntity] = []

    for brand in sorted(BRANDS):
        if brand in normalized:
            entities.append(
                ExtractedEntity(type=EntityType.BRAND, value=brand.title(), confidence=0.9)
            )
            break

    product = _detect_product(normalized)
    if product:
        entities.append(ExtractedEntity(type=EntityType.PRODUCT, value=product, confidence=0.85))

    budget = _detect_budget(normalized)
    if budget:
        amount, currency = budget
        entities.append(
            ExtractedEntity(
                type=EntityType.BUDGET,
                value=str(amount),
                confidence=0.9,
                attributes={"currency": currency},
            )
        )
        entities.append(ExtractedEntity(type=EntityType.CURRENCY, value=currency, confidence=0.9))

    if any(word in normalized for word in ("notify", "watch", "monitor", "price drop", "هبط")):
        entities.append(ExtractedEntity(type=EntityType.INTENT, value="watch", confidence=0.75))
    else:
        entities.append(ExtractedEntity(type=EntityType.INTENT, value="search", confidence=0.8))

    if locale_hint:
        entities.append(
            ExtractedEntity(
                type=EntityType.SITE,
                value=locale_hint,
                confidence=0.5,
                attributes={"kind": "locale_hint"},
            )
        )

    return entities


def _detect_product(normalized: str) -> str | None:
    for product, keywords in PRODUCT_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords):
            return product
    return None


def _detect_budget(normalized: str) -> tuple[float, str] | None:
    matches = list(BUDGET_PATTERN.finditer(normalized))
    if not matches:
        return None

    best = max(matches, key=lambda match: float(match.group("amount").replace(",", ".")))
    amount = float(best.group("amount").replace(",", "."))
    raw_currency = (best.group("currency") or "MAD").upper()
    currency = "MAD" if raw_currency in {"DH", "DHS", "DIRHAM", "DIRHAMS", "درهم"} else raw_currency
    return amount, currency
