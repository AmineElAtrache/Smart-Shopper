"""Shared city/color matching for scrapers and the decision agent."""

from __future__ import annotations

import re

from shared.events.schemas import ProductQuery, RawProduct

COLOR_ALIASES: dict[str, set[str]] = {
    "black": {"black", "noir", "siyah", "kehla", "k7la", "kahla"},
    "white": {"white", "blanc", "beyaz", "biad", "byad"},
    "blue": {"blue", "bleu", "mavi"},
    "red": {"red", "rouge", "kirmizi", "7mer", "7mar"},
    "green": {"green", "vert", "yesil", "khdar"},
    "gray": {"gray", "grey", "gris", "gri"},
    "grey": {"gray", "grey", "gris", "gri"},
    "gold": {"gold", "or", "dore", "doré", "dhahabi"},
    "silver": {"silver", "argent", "fidda"},
    "brown": {"brown", "marron", "kahverengi", "boni"},
}

CITY_ALIASES: dict[str, set[str]] = {
    "casablanca": {"casablanca", "casa", "dar el beida", "dar el-beida", "dar el beïda"},
    "rabat": {"rabat", "rbat"},
    "fes": {"fes", "fez", "fès"},
    "marrakech": {"marrakech", "marrakesh"},
    "tanger": {"tanger", "tangier", "tanja"},
    "agadir": {"agadir"},
    "mohammedia": {"mohammedia"},
    "kenitra": {"kenitra", "kénitra"},
    "meknes": {"meknes", "meknès"},
    "oujda": {"oujda"},
    "temara": {"temara", "tmara"},
    "el_jadida": {"el jadida", "el-jadida", "jadida"},
}


def normalize_token(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"[_\W]+", " ", value.lower())).strip()


def color_terms(color: str | None) -> set[str]:
    if not color:
        return set()
    key = normalize_token(color)
    return {term.lower() for term in COLOR_ALIASES.get(key, {key})}


def resolve_city_key(city: str | None) -> str | None:
    if not city:
        return None
    key = normalize_token(city).replace(" ", "_")
    if key in CITY_ALIASES:
        return key
    for canonical, aliases in CITY_ALIASES.items():
        alias_keys = {normalize_token(alias).replace(" ", "_") for alias in aliases}
        if key in alias_keys:
            return canonical
    return key


def city_terms(city: str | None) -> set[str]:
    if not city:
        return set()
    canonical = resolve_city_key(city) or normalize_token(city)
    canonical_key = canonical.replace(" ", "_")
    aliases = CITY_ALIASES.get(canonical_key, {canonical.replace("_", " ")})
    terms = {normalize_token(term) for term in aliases}
    terms.add(normalize_token(canonical))
    return {term for term in terms if term}


def product_searchable_text(product: RawProduct) -> str:
    metadata_bits = " ".join(str(value) for value in (product.metadata or {}).values())
    return normalize_token(f"{product.title} {product.url} {metadata_bits} {product.seller or ''}")


def matches_color_in_text(text: str, query: ProductQuery) -> bool:
    if not query.color:
        return True
    lowered = normalize_token(text)
    return any(term in lowered for term in color_terms(query.color))


def matches_city_in_text(text: str, query: ProductQuery) -> bool:
    if not query.city:
        return True
    lowered = normalize_token(text)
    return any(term in lowered for term in city_terms(query.city))


def matches_city_and_color(product: RawProduct, query: ProductQuery) -> bool:
    searchable = product_searchable_text(product)
    return matches_color_in_text(searchable, query) and matches_city_in_text(searchable, query)
