"""Decision scoring based on the architecture report's 100-point system."""

from __future__ import annotations

import re

from agents.decision.tools.dedup_engine import deduplicate_products
from agents.decision.tools.fraud_detector import fraud_penalty
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

PRODUCT_ALIASES = {
    "phone": {
        "phone", "phones", "smartphone", "telephone", "telephones", "mobile",
        "iphone", "galaxy", "redmi", "xiaomi", "itel", "infinix", "tecno",
        "oppo", "realme", "huawei", "honor", "nokia", "vivo",
    },
    "laptop": {
        "laptop", "notebook", "macbook", "thinkpad", "ideapad", "ordinateur portable",
        "pc portable", "portable", "omen", "victus", "latitude", "inspiron", "vivobook",
        "zenbook", "elitebook", "probook", "legion", "loq", "rog", "predator",
    },
    "pc": {
        "pc", "ordinateur", "desktop", "ordinateur bureau", "unite centrale", "tour gamer",
        "gaming pc", "workstation", "omen", "victus",
    },
    "car": {"car", "voiture", "tomobile", "automobile", "golf", "clio", "dacia", "renault", "volkswagen", "bmw"},
    "fridge": {"fridge", "refrigerator", "refrigerateur", "telaja"},
    "tv": {"tv", "television", "televiseur", "smart tv"},
}

PRODUCT_SYNONYMS = {
    "phones": "phone",
    "telephone": "phone",
    "telephones": "phone",
    "mobile": "phone",
    "smartphone": "phone",
    "ordinateur portable": "laptop",
    "pc portable": "laptop",
    "notebook": "laptop",
    "tomobile": "car",
    "voiture": "car",
    "automobile": "car",
    "telaja": "fridge",
    "refrigerator": "fridge",
    "refrigerateur": "fridge",
}

NEGATIVE_TERMS = {
    "phone": {
        "headphone", "headphones", "earphone", "earphones", "microphone", "micro", "charger",
        "chargeur", "case", "cover", "coque", "cable", "protector", "glass", "support",
        "whey", "protein", "nitrotech", "stand",
    },
    "laptop": {
        "stand", "support", "sleeve", "bag", "sac", "charger", "chargeur", "battery",
        "adapter", "dock", "cooler", "cooling", "clavier", "keyboard", "mouse", "souris",
    },
    "pc": {"keyboard", "mouse", "souris", "clavier", "screen", "monitor", "stand", "support"},
}

NOISY_TITLE_TERMS = {
    "accueil", "contact", "plan du site", "notre magasin", "chers clients", "livraison",
    "paiement", "cookies", "conditions generales", "+ lire plus",
}


def rank_products(products: list[RawProduct], query: ProductQuery) -> list[RankedProduct]:
    unique_products = deduplicate_products(products)
    relevant_products = filter_relevant_products(unique_products, query)
    ranked = [score_product(product, query) for product in relevant_products]
    return _diversify_top_sources(sorted(ranked, key=lambda product: product.score, reverse=True))


def filter_relevant_products(products: list[RawProduct], query: ProductQuery) -> list[RawProduct]:
    """Keep products that match the requested item, dropping accessories and scraped page noise."""
    requested = _canonical_product(query.product)
    if not requested:
        return [product for product in products if not _is_noisy_listing(product)]
    return [product for product in products if _matches_query_product(product, query, requested)]




def _diversify_top_sources(products: list[RankedProduct], *, top_n: int = 3, max_per_source: int = 2) -> list[RankedProduct]:
    """Avoid showing the first three options from only one website when alternatives exist."""
    if len(products) <= top_n:
        return products

    selected: list[RankedProduct] = []
    deferred: list[RankedProduct] = []
    source_counts: dict[str, int] = {}

    for product in products:
        source = product.source.lower()
        if len(selected) < top_n and source_counts.get(source, 0) < max_per_source:
            selected.append(product)
            source_counts[source] = source_counts.get(source, 0) + 1
        else:
            deferred.append(product)

    if len(selected) < top_n:
        needed = top_n - len(selected)
        selected.extend(deferred[:needed])
        deferred = deferred[needed:]

    selected_ids = {id(product) for product in selected}
    remainder = [product for product in products if id(product) not in selected_ids]
    return selected + remainder

def score_product(product: RawProduct, query: ProductQuery) -> RankedProduct:
    breakdown = ScoreBreakdown(
        price=_price_score(product, query),
        trust=_trust_score(product, query),
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


def _trust_score(product: RawProduct, query: ProductQuery) -> int:
    source = product.source.lower()
    seller = (product.seller or "").lower()

    base_score = 15
    for trusted_source, score in TRUSTED_SOURCES.items():
        if trusted_source in source or trusted_source in seller:
            base_score = score
            break
    return max(0, base_score - fraud_penalty(product, query))


def _quality_score(product: RawProduct, query: ProductQuery) -> int:
    score = 10
    title = _normalize(product.title)
    requested = _canonical_product(query.product)

    if requested and _contains_any(title, PRODUCT_ALIASES.get(requested, {requested})):
        score += 5
    if query.brand and _normalize(query.brand) in title:
        score += 4
    if product.rating is not None:
        score += round((product.rating / 5) * 4)

    return min(score, 20)


def _availability_score(product: RawProduct) -> int:
    if product.availability == Availability.IN_STOCK:
        return 10
    if product.availability == Availability.UNKNOWN:
        return 5
    return 0


def _matches_query_product(product: RawProduct, query: ProductQuery, requested: str) -> bool:
    title = _normalize(product.title)
    if _is_noisy_listing(product):
        return False
    if _contains_any(title, NEGATIVE_TERMS.get(requested, set())):
        return False

    aliases = PRODUCT_ALIASES.get(requested, {requested})
    if _contains_any(title, aliases):
        return True

    if query.brand and _normalize(query.brand) in title:
        return True

    return False


def _is_noisy_listing(product: RawProduct) -> bool:
    title = _normalize(product.title)
    if str(product.url).rstrip("/").count("/") <= 2 and len(title) > 120:
        return True
    return _contains_any(title, NOISY_TITLE_TERMS)


def _canonical_product(product: str | None) -> str | None:
    if not product:
        return None
    normalized = _normalize(product)
    if normalized in PRODUCT_ALIASES:
        return normalized
    return PRODUCT_SYNONYMS.get(normalized, normalized)


def _contains_any(text: str, terms: set[str]) -> bool:
    return any(_has_term(text, term) for term in terms)


def _has_term(text: str, term: str) -> bool:
    normalized_term = _normalize(term)
    if " " in normalized_term:
        return normalized_term in text
    return re.search(rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])", text) is not None


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w]+", " ", value.lower())).strip()

