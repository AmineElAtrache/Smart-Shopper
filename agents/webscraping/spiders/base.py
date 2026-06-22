"""Shared helpers for website scrapers."""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import urljoin

from shared.events.schemas import ProductQuery, ScrapeTaskAssigned

MAD_PRICE_RE = re.compile(r"(?P<amount>\d[\d\s.,]*)\s*(?:MAD|DH|DHS|درهم)?", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
COLOR_ALIASES = {
    "black": {"black", "noir", "siyah"},
    "white": {"white", "blanc", "beyaz"},
    "blue": {"blue", "bleu", "mavi"},
    "red": {"red", "rouge", "kirmizi", "kırmızı"},
    "green": {"green", "vert", "yesil", "yeşil"},
    "gray": {"gray", "grey", "gris", "gri"},
    "grey": {"gray", "grey", "gris", "gri"},
    "gold": {"gold", "or", "dore", "doré"},
    "silver": {"silver", "argent"},
    "brown": {"brown", "marron", "kahverengi"},
}
PRODUCT_ALIASES = {
    "phone": {"phone", "telephone", "téléphone", "smartphone", "gsm", "galaxy"},
    "smartphone": {"phone", "telephone", "téléphone", "smartphone", "gsm", "galaxy"},
    "telephone": {"phone", "telephone", "téléphone", "smartphone", "gsm", "galaxy"},
    "laptop": {"laptop", "pc", "ordinateur", "portable"},
    "shoes": {"shoes", "shoe", "chaussures", "baskets"},
    "shoe": {"shoes", "shoe", "chaussures", "baskets"},
    "chair": {"chair", "chaise"},
    "apartment": {"apartment", "appartement", "appartements"},
}


def build_search_text(task: ScrapeTaskAssigned) -> str:
    query = task.query
    parts = [query.brand, query.product, query.color]
    return " ".join(part for part in parts if part).strip() or "phone"


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = TAG_RE.sub(" ", value)
    value = unescape(value)
    return SPACE_RE.sub(" ", value).strip()


def parse_mad_price(value: str | None) -> float | None:
    text = clean_text(value)
    match = MAD_PRICE_RE.search(text)
    if not match:
        return None
    amount = match.group("amount")
    amount = amount.replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return float(amount)
    except ValueError:
        return None


def absolute_url(base_url: str, href: str | None) -> str | None:
    if not href:
        return None
    return urljoin(base_url, href)


def budget_allows(price: float, query: ProductQuery) -> bool:
    if query.budget is None:
        return True
    return price <= query.budget * 1.25


def has_any_term(searchable_text: str, terms: set[str]) -> bool:
    lowered = searchable_text.lower()
    return any(term.lower() in lowered for term in terms)


def matches_brand(searchable_text: str, query: ProductQuery) -> bool:
    return not query.brand or query.brand.lower() in searchable_text.lower()


def matches_product(searchable_text: str, query: ProductQuery, aliases: dict[str, set[str]] | None = None) -> bool:
    if not query.product:
        return True
    alias_map = {**PRODUCT_ALIASES, **(aliases or {})}
    terms = alias_map.get(query.product.lower(), {query.product.lower()})
    return has_any_term(searchable_text, terms)


def matches_color(searchable_text: str, query: ProductQuery, aliases: dict[str, set[str]] | None = None) -> bool:
    if not query.color:
        return True
    alias_map = {**COLOR_ALIASES, **(aliases or {})}
    terms = alias_map.get(query.color.lower(), {query.color.lower()})
    return has_any_term(searchable_text, terms)


def matches_city(searchable_text: str, query: ProductQuery) -> bool:
    return not query.city or query.city.lower() in searchable_text.lower()
