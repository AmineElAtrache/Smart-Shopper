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
    "phone": {"phone", "smartphone", "telephone", "telephone", "tel", "iphone"},
    "laptop": {"laptop", "pc", "ordinateur", "portable", "pc portable"},
    "tablet": {"tablet", "tablette", "ipad"},
    "headphones": {"headphones", "casque", "ecouteurs", "ecouteurs"},
}

CITY_ALIASES = {
    "casablanca": "casablanca",
    "casa": "casablanca",
    "rabat": "rabat",
    "marrakech": "marrakech",
    "marrakesh": "marrakech",
    "tanger": "tanger",
    "tangier": "tanger",
    "fes": "fes",
    "fez": "fes",
    "agadir": "agadir",
    "meknes": "meknes",
    "oujda": "oujda",
    "kenitra": "kenitra",
    "tetouan": "tetouan",
    "sale": "sale",
}

COLOR_ALIASES = {
    "black": "black",
    "noir": "black",
    "k7al": "black",
    "white": "white",
    "blanc": "white",
    "biad": "white",
    "blue": "blue",
    "bleu": "blue",
    "red": "red",
    "rouge": "red",
    "green": "green",
    "vert": "green",
    "gray": "gray",
    "grey": "gray",
    "gris": "gray",
    "gold": "gold",
    "or": "gold",
    "silver": "silver",
    "argent": "silver",
}

BUDGET_PATTERN = re.compile(
    r"(?P<amount>\d+(?:[.,]\d+)?)\s*(?P<currency>mad|dh|dhs|dirham|dirhams)?",
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

    city = _detect_alias(normalized, CITY_ALIASES)
    if city:
        entities.append(ExtractedEntity(type=EntityType.CITY, value=city, confidence=0.8))

    color = _detect_alias(normalized, COLOR_ALIASES)
    if color:
        entities.append(ExtractedEntity(type=EntityType.COLOR, value=color, confidence=0.8))

    budget = _detect_budget(normalized)
    if budget:
        amount, currency = budget
        attributes = {"currency": currency}
        entities.append(
            ExtractedEntity(
                type=EntityType.PRICE,
                value=str(amount),
                confidence=0.9,
                attributes=attributes,
            )
        )
        entities.append(
            ExtractedEntity(
                type=EntityType.BUDGET,
                value=str(amount),
                confidence=0.9,
                attributes=attributes,
            )
        )
        entities.append(ExtractedEntity(type=EntityType.CURRENCY, value=currency, confidence=0.9))

    if any(word in normalized for word in ("notify", "watch", "monitor", "price drop", "hbet")):
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


def _detect_alias(normalized: str, aliases: dict[str, str]) -> str | None:
    tokens = set(re.findall(r"[\w]+", normalized))
    for alias, value in aliases.items():
        if alias in tokens:
            return value
    return None


def _detect_budget(normalized: str) -> tuple[float, str] | None:
    matches = list(BUDGET_PATTERN.finditer(normalized))
    if not matches:
        return None

    best = max(matches, key=lambda match: float(match.group("amount").replace(",", ".")))
    amount = float(best.group("amount").replace(",", "."))
    raw_currency = (best.group("currency") or "MAD").upper()
    currency = "MAD" if raw_currency in {"DH", "DHS", "DIRHAM", "DIRHAMS"} else raw_currency
    return amount, currency
