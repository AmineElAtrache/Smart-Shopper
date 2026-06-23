"""NER service adapter for Moroccan shopping queries.

The production path uses the fine-tuned Hugging Face token-classification model.
A rule-based fallback stays available so local tests and development keep working
when model dependencies or cached weights are not installed yet.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from typing import Any

from shared.events.schemas import EntityType, ExtractedEntity

DEFAULT_MODEL_ID = "ElAtrachAMINE/darija-ner-xlmroberta"

BRANDS = {
    "samsung": "Samsung",
    "iphone": "Apple",
    "apple": "Apple",
    "xiaomi": "Xiaomi",
    "redmi": "Xiaomi",
    "oppo": "Oppo",
    "hp": "HP",
    "dell": "Dell",
    "lenovo": "Lenovo",
    "asus": "Asus",
    "acer": "Acer",
    "volkswagen": "Volkswagen",
    "vw": "Volkswagen",
    "golf": "Volkswagen",
    "bmw": "BMW",
    "mercedes": "Mercedes",
    "renault": "Renault",
    "dacia": "Dacia",
    "peugeot": "Peugeot",
    "kia": "Kia",
    "hyundai": "Hyundai",
    "toyota": "Toyota",
}

PRODUCT_KEYWORDS = {
    "phone": {"phone", "smartphone", "telephone", "tel", "iphone"},
    "laptop": {"laptop", "pc", "ordinateur", "portable", "pc portable"},
    "tablet": {"tablet", "tablette", "ipad"},
    "headphones": {"headphones", "casque", "ecouteurs"},
    "golf": {"golf"},
    "car": {"voiture", "tomobile", "tomobil", "tonobile", "tonobil", "auto", "car"},
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
    "k7la": "black",
    "kehla": "black",
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

LABEL_ALIASES = {
    "TARGET": EntityType.PRODUCT,
    "PRODUCT": EntityType.PRODUCT,
    "ITEM": EntityType.PRODUCT,
    "CATEGORY": EntityType.PRODUCT,
    "MODEL": EntityType.PRODUCT,
    "BRAND": EntityType.BRAND,
    "PRICE": EntityType.PRICE,
    "BUDGET": EntityType.BUDGET,
    "AMOUNT": EntityType.BUDGET,
    "CITY": EntityType.CITY,
    "LOCATION": EntityType.CITY,
    "COLOR": EntityType.COLOR,
    "QUALITY": EntityType.QUALITY,
    "STATE": EntityType.QUALITY,
    "INTENT": EntityType.INTENT,
    "SITE": EntityType.SITE,
}

BUDGET_PATTERN = re.compile(
    r"(?P<amount>\d+(?:[.,]\d+)?)\s*(?P<currency>mad|dh|dhs|dirham|dirhams)?",
    re.IGNORECASE,
)
TOKEN_PATTERN = re.compile(r"[\w]+", re.UNICODE)


def extract_entities(text: str, locale_hint: str | None = None) -> list[ExtractedEntity]:
    """Extract normalized entities for the orchestrator.

    The public contract intentionally stays stable: callers receive shared
    ``ExtractedEntity`` objects no matter whether the Hugging Face model or the
    local fallback produced the prediction.
    """
    model_entities = _extract_with_model(text)
    fallback_entities = _extract_with_rules(text, locale_hint=locale_hint)
    return _merge_entities(model_entities, fallback_entities)


def _extract_with_model(text: str) -> list[ExtractedEntity]:
    backend = os.getenv("SMART_SHOPPER_NER_BACKEND", "auto").lower()
    if backend == "rules":
        return []

    try:
        model_id = os.getenv("SMART_SHOPPER_NER_MODEL", DEFAULT_MODEL_ID)
        allow_download = backend == "hf"
        predictions = _get_pipeline(model_id, allow_download)(text)
    except Exception:
        if backend == "hf":
            raise
        return []

    entities: list[ExtractedEntity] = []
    for prediction in predictions:
        entity = _prediction_to_entity(prediction)
        if entity is not None:
            entities.extend(_expand_price_entity(entity))
    return entities


@lru_cache(maxsize=2)
def _get_pipeline(model_id: str, allow_download: bool) -> Any:
    from transformers import AutoModelForTokenClassification, AutoTokenizer, pipeline

    tokenizer = AutoTokenizer.from_pretrained(model_id, local_files_only=not allow_download)
    model = AutoModelForTokenClassification.from_pretrained(
        model_id,
        local_files_only=not allow_download,
    )
    return pipeline(
        "token-classification",
        model=model,
        tokenizer=tokenizer,
        aggregation_strategy="simple",
    )


def _prediction_to_entity(prediction: dict[str, Any]) -> ExtractedEntity | None:
    raw_label = str(
        prediction.get("entity_group")
        or prediction.get("entity")
        or prediction.get("label")
        or ""
    )
    label = raw_label.replace("B-", "").replace("I-", "").upper()
    entity_type = LABEL_ALIASES.get(label)
    if entity_type is None:
        return None

    value = _normalize_value(entity_type, str(prediction.get("word") or ""))
    if not value:
        return None

    confidence = float(prediction.get("score") or 0.75)
    attributes: dict[str, str] = {}
    if entity_type in {EntityType.PRICE, EntityType.BUDGET}:
        amount, currency = _normalize_amount(value)
        if amount is None:
            return None
        value = str(amount)
        attributes["currency"] = currency

    return ExtractedEntity(
        type=entity_type,
        value=value,
        confidence=max(0.0, min(confidence, 1.0)),
        attributes=attributes,
    )


def _extract_with_rules(text: str, locale_hint: str | None = None) -> list[ExtractedEntity]:
    normalized = text.lower().strip()
    entities: list[ExtractedEntity] = []

    brand = _detect_brand(normalized)
    if brand:
        entities.append(ExtractedEntity(type=EntityType.BRAND, value=brand, confidence=0.9))

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


def _merge_entities(
    primary: list[ExtractedEntity], fallback: list[ExtractedEntity]
) -> list[ExtractedEntity]:
    merged: list[ExtractedEntity] = []
    seen: set[EntityType] = set()

    for entity in [*primary, *fallback]:
        if entity.type in seen:
            continue
        merged.append(entity)
        seen.add(entity.type)

    return merged


def _expand_price_entity(entity: ExtractedEntity) -> list[ExtractedEntity]:
    if entity.type not in {EntityType.PRICE, EntityType.BUDGET}:
        return [entity]

    price = ExtractedEntity(
        type=EntityType.PRICE,
        value=entity.value,
        confidence=entity.confidence,
        attributes=entity.attributes,
    )
    budget = ExtractedEntity(
        type=EntityType.BUDGET,
        value=entity.value,
        confidence=entity.confidence,
        attributes=entity.attributes,
    )
    currency = ExtractedEntity(
        type=EntityType.CURRENCY,
        value=entity.attributes.get("currency", "MAD"),
        confidence=entity.confidence,
    )
    return [price, budget, currency]


def _normalize_value(entity_type: EntityType, value: str) -> str:
    value = value.replace("##", "").strip(" ,.;:!?\"'").strip()
    compact = value.lower()
    if entity_type == EntityType.BRAND:
        return BRANDS.get(compact, value.title())
    if entity_type == EntityType.CITY:
        return CITY_ALIASES.get(compact, compact)
    if entity_type == EntityType.COLOR:
        return COLOR_ALIASES.get(compact, compact)
    if entity_type == EntityType.INTENT:
        return "watch" if compact in {"watch", "monitor", "notify", "hbet"} else "search"
    return compact if entity_type in {EntityType.PRODUCT, EntityType.QUALITY, EntityType.SITE} else value


def _normalize_amount(value: str) -> tuple[float | None, str]:
    match = BUDGET_PATTERN.search(value)
    if not match:
        return None, "MAD"
    amount = float(match.group("amount").replace(",", "."))
    raw_currency = (match.group("currency") or "MAD").upper()
    currency = "MAD" if raw_currency in {"DH", "DHS", "DIRHAM", "DIRHAMS"} else raw_currency
    return amount, currency


def _detect_brand(normalized: str) -> str | None:
    tokens = set(TOKEN_PATTERN.findall(normalized))
    for alias, brand in BRANDS.items():
        if alias in tokens:
            return brand
    return None


def _detect_product(normalized: str) -> str | None:
    for product, keywords in PRODUCT_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords):
            return product
    return None


def _detect_alias(normalized: str, aliases: dict[str, str]) -> str | None:
    tokens = set(TOKEN_PATTERN.findall(normalized))
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
