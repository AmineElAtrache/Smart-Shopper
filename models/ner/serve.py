"""NER service adapter for Moroccan shopping queries.

The production path uses the fine-tuned Hugging Face token-classification model.
A preprocessing layer cleans noisy Darija/French/English shopping text before
model inference, and context enrichment fills normalized fields that token
models can miss, such as product models in "hp omen" or Darija price aliases.
"""

from __future__ import annotations

import os
import re
import unicodedata
from difflib import SequenceMatcher
from functools import lru_cache
from typing import Any

from shared.events.schemas import EntityType, ExtractedEntity

try:
    from rapidfuzz import fuzz, process
except ImportError:  # pragma: no cover - rapidfuzz is declared in project deps.
    fuzz = None
    process = None

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
    "fridge": {"fridge", "refrigerator", "refrigerateur", "frigo", "telaja", "thalaja"},
    "golf": {"golf"},
    "car": {"voiture", "tomobile", "tomobil", "tonobile", "tonobil", "auto", "car"},
}
PRODUCT_VALUE_ALIASES = {
    "pc": "laptop",
    "ordinateur": "laptop",
    "portable": "laptop",
    "pc portable": "laptop",
    "telephone": "phone",
    "tel": "phone",
    "smartphone": "phone",
    "voiture": "car",
    "telaja": "fridge",
    "thalaja": "fridge",
    "frigo": "fridge",
    "refrigerateur": "fridge",
    "refrigerator": "fridge",
}
QUALITY_ALIASES = {
    "jdida": "new",
    "jdid": "new",
    "new": "new",
    "neuf": "new",
    "occasion": "used",
    "mosta3mal": "used",
    "used": "used",
    "maghalyach": "affordable",
    "rkhis": "affordable",
    "nadi": "good",
}
KNOWN_BRAND_VALUES = {brand.lower() for brand in BRANDS.values()} | set(BRANDS)
UNKNOWN_BRAND_MIN_CONFIDENCE = 0.8

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
    "kahla": "black",
    "white": "white",
    "blanc": "white",
    "biad": "white",
    "byad": "white",
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

SPELLING_ALIASES = {
    "samsng": "samsung",
    "samsong": "samsung",
    "samsonge": "samsung",
    "iphon": "iphone",
    "iphne": "iphone",
    "appel": "apple",
    "hewlett": "hp",
    "packard": "hp",
    "hpq": "hp",
    "casaa": "casablanca",
    "casablaca": "casablanca",
    "casablnca": "casablanca",
    "rbaat": "rabat",
    "marrakesh": "marrakech",
    "f?s": "fes",
    "fez": "fes",
    "tomobile": "voiture",
    "tomobil": "voiture",
    "tonobile": "voiture",
    "tonobil": "voiture",
    "tomobila": "voiture",
    "telaja": "fridge",
    "thalaja": "fridge",
    "frigo": "fridge",
    "refrigerateur": "fridge",
    "k7la": "black",
    "k7al": "black",
    "kehla": "black",
    "kahla": "black",
    "noire": "black",
    "phne": "phone",
    "fone": "phone",
    "telephon": "telephone",
    "labtop": "laptop",
    "laptope": "laptop",
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
    r"(?<![A-Za-z0-9])(?P<amount>\d+(?:[.,]\d+)?)\s*"
    r"(?P<currency>mad|ddh|dh|dhs|dirham|dirhams)?(?![A-Za-z0-9])",
    re.IGNORECASE,
)
TOKEN_PATTERN = re.compile(r"[\w]+", re.UNICODE)
MODEL_STOP_TOKENS = {
    "b",
    "bi",
    "f",
    "fi",
    "fel",
    "l",
    "li",
    "we",
    "w",
    "ou",
    "o",
    "ana",
    "3endi",
    "hi",
    "budget",
    "price",
    "prix",
    "under",
    "ta7t",
    "avec",
    "with",
}
MODEL_IGNORED_TOKENS = {
    "bghit",
    "baghi",
    "kan9lb",
    "nqelleb",
    "chi",
    "wahed",
    "jdida",
    "mosta3mal",
    "used",
    "new",
    "neuf",
    "occasion",
    "mad",
    "dh",
    "dhs",
    "dirham",
    "dirhams",
}
FUZZY_CHOICES = sorted(
    set(BRANDS) | set(CITY_ALIASES) | set(COLOR_ALIASES) | {kw for kws in PRODUCT_KEYWORDS.values() for kw in kws}
)
FUZZY_REPLACEMENTS = {
    **{alias: alias for alias in BRANDS},
    **CITY_ALIASES,
    **COLOR_ALIASES,
    **{keyword: product for product, keywords in PRODUCT_KEYWORDS.items() for keyword in keywords},
}


def extract_entities(text: str, locale_hint: str | None = None) -> list[ExtractedEntity]:
    """Extract normalized entities for the orchestrator.

    ``SMART_SHOPPER_NER_BACKEND=auto`` is the default production mode. It loads
    the Hugging Face model from the local cache when available, or downloads it
    once and reuses the cached files afterwards.
    """
    normalized_text = _preprocess_text(text)
    model_entities = _extract_with_model(normalized_text)
    context_entities = _derive_context_entities(
        original_text=text,
        normalized_text=normalized_text,
        locale_hint=locale_hint,
    )
    return _merge_entities(model_entities, context_entities)


def _preprocess_text(text: str) -> str:
    ascii_text = _strip_accents(text.lower())
    tokens = TOKEN_PATTERN.findall(ascii_text)
    normalized_tokens = [_normalize_token(token) for token in tokens]
    return " ".join(normalized_tokens)


def _strip_accents(text: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(character)
    )


def _normalize_token(token: str) -> str:
    if token in SPELLING_ALIASES:
        return SPELLING_ALIASES[token]
    if len(token) < 4 or token.isdigit():
        return token

    match = _fuzzy_match(token, FUZZY_CHOICES, threshold=88)
    if match is None:
        return token
    return FUZZY_REPLACEMENTS.get(match, match)


def _fuzzy_match(token: str, choices: list[str], threshold: int) -> str | None:
    if process is not None and fuzz is not None:
        result = process.extractOne(token, choices, scorer=fuzz.WRatio, score_cutoff=threshold)
        return str(result[0]) if result else None

    best_choice = None
    best_score = 0.0
    for choice in choices:
        score = SequenceMatcher(None, token, choice).ratio() * 100
        if score > best_score:
            best_choice = choice
            best_score = score
    return best_choice if best_choice is not None and best_score >= threshold else None


def _extract_with_model(text: str) -> list[ExtractedEntity]:
    backend = os.getenv("SMART_SHOPPER_NER_BACKEND", "auto").lower()
    if backend not in {"auto", "hf"}:
        raise ValueError("SMART_SHOPPER_NER_BACKEND must be 'auto' or 'hf'")

    model_id = os.getenv("SMART_SHOPPER_NER_MODEL", DEFAULT_MODEL_ID)
    predictions = _get_pipeline(model_id)(text)

    entities: list[ExtractedEntity] = []
    for prediction in predictions:
        entity = _prediction_to_entity(prediction)
        if entity is not None:
            entities.extend(_expand_price_entity(entity))
    return entities


@lru_cache(maxsize=1)
def _get_pipeline(model_id: str) -> Any:
    from transformers import AutoModelForTokenClassification, AutoTokenizer, pipeline

    tokenizer = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForTokenClassification.from_pretrained(model_id)
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
    if entity_type == EntityType.BRAND and _is_low_confidence_unknown_brand(value, confidence):
        return None

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


def _derive_context_entities(
    *, original_text: str, normalized_text: str, locale_hint: str | None = None
) -> list[ExtractedEntity]:
    entities: list[ExtractedEntity] = []

    brand = _detect_brand(normalized_text)
    if brand:
        entities.append(ExtractedEntity(type=EntityType.BRAND, value=brand, confidence=0.7))

    product = _detect_product(normalized_text) or _detect_model_after_brand(normalized_text)
    if product:
        entities.append(ExtractedEntity(type=EntityType.PRODUCT, value=product, confidence=0.7))

    city = _detect_alias(normalized_text, CITY_ALIASES)
    if city:
        entities.append(ExtractedEntity(type=EntityType.CITY, value=city, confidence=0.7))

    quality = _detect_alias(normalized_text, QUALITY_ALIASES)
    if quality:
        entities.append(ExtractedEntity(type=EntityType.QUALITY, value=quality, confidence=0.7))

    color = _detect_alias(normalized_text, COLOR_ALIASES)
    if color:
        entities.append(ExtractedEntity(type=EntityType.COLOR, value=color, confidence=0.7))

    budget = _detect_budget(normalized_text)
    if budget:
        amount, currency = budget
        attributes = {"currency": currency}
        entities.append(
            ExtractedEntity(
                type=EntityType.PRICE,
                value=str(amount),
                confidence=0.7,
                attributes=attributes,
            )
        )
        entities.append(
            ExtractedEntity(
                type=EntityType.BUDGET,
                value=str(amount),
                confidence=0.7,
                attributes=attributes,
            )
        )
        entities.append(ExtractedEntity(type=EntityType.CURRENCY, value=currency, confidence=0.7))

    if any(word in normalized_text for word in ("notify", "watch", "monitor", "price drop", "hbet")):
        entities.append(ExtractedEntity(type=EntityType.INTENT, value="watch", confidence=0.7))
    else:
        entities.append(ExtractedEntity(type=EntityType.INTENT, value="search", confidence=0.7))

    if locale_hint:
        entities.append(
            ExtractedEntity(
                type=EntityType.SITE,
                value=locale_hint,
                confidence=0.5,
                attributes={"kind": "locale_hint", "original_text": original_text},
            )
        )

    return entities


def _merge_entities(
    primary: list[ExtractedEntity], context: list[ExtractedEntity]
) -> list[ExtractedEntity]:
    merged: list[ExtractedEntity] = []
    seen: set[EntityType] = set()

    for entity in [*primary, *context]:
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
    if entity_type == EntityType.PRODUCT:
        return PRODUCT_VALUE_ALIASES.get(compact, compact)
    if entity_type == EntityType.CITY:
        return CITY_ALIASES.get(compact, compact)
    if entity_type == EntityType.COLOR:
        return COLOR_ALIASES.get(compact, compact)
    if entity_type == EntityType.QUALITY:
        return QUALITY_ALIASES.get(compact, compact)
    if entity_type == EntityType.INTENT:
        return "watch" if compact in {"watch", "monitor", "notify", "hbet"} else "search"
    return compact if entity_type in {EntityType.QUALITY, EntityType.SITE} else value


def _is_low_confidence_unknown_brand(value: str, confidence: float) -> bool:
    return value.lower() not in KNOWN_BRAND_VALUES and confidence < UNKNOWN_BRAND_MIN_CONFIDENCE


def _normalize_amount(value: str) -> tuple[float | None, str]:
    match = BUDGET_PATTERN.search(value)
    if not match:
        return None, "MAD"
    amount = float(match.group("amount").replace(",", "."))
    raw_currency = (match.group("currency") or "MAD").upper()
    currency = "MAD" if raw_currency in {"DDH", "DH", "DHS", "DIRHAM", "DIRHAMS"} else raw_currency
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


def _detect_model_after_brand(normalized: str) -> str | None:
    tokens = TOKEN_PATTERN.findall(normalized)
    blocked = (
        set(BRANDS)
        | set(CITY_ALIASES)
        | set(COLOR_ALIASES)
        | set(QUALITY_ALIASES)
        | MODEL_IGNORED_TOKENS
    )

    for index, token in enumerate(tokens):
        if token not in BRANDS:
            continue
        for candidate in tokens[index + 1 : index + 4]:
            if candidate in MODEL_STOP_TOKENS:
                break
            if candidate in blocked or BUDGET_PATTERN.fullmatch(candidate):
                continue
            if len(candidate) >= 2:
                return candidate
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
