"""Bringo by Carrefour (bringo.ma) scraper provider."""

from __future__ import annotations

import json
import re
from urllib.parse import quote_plus

import httpx

from agents.webscraping.spiders.base import (
    budget_allows,
    build_search_text,
    clean_text,
    matches_brand,
    matches_color,
    matches_product,
)
from shared.events.schemas import Availability, RawProduct, ScrapeTaskAssigned

BRINGO_BASE_URL = "https://www.bringo.ma/fr_MA"
BRINGO_SEARCH_API = "https://ac.cnstrc.com/v1/autocomplete/{query}"
BRINGO_API_KEY = "key_RXaj9cqebJi8jKk8"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
PRODUCT_TERMS = {
    "milk": "lait",
    "coffee": "cafe",
    "rice": "riz",
    "oil": "huile",
    "sugar": "sucre",
    "tea": "the",
    "water": "eau",
    "detergent": "lessive",
    "bread": "pain",
    "eggs": "oeufs",
}
PRODUCT_MATCH_TERMS = {
    "milk": {"milk", "lait"},
    "coffee": {"coffee", "cafe", "café"},
    "rice": {"rice", "riz"},
    "oil": {"oil", "huile"},
    "sugar": {"sugar", "sucre"},
    "tea": {"tea", "the", "thé"},
    "water": {"water", "eau"},
    "detergent": {"detergent", "lessive"},
    "bread": {"bread", "pain"},
    "eggs": {"eggs", "oeufs", "œufs"},
}


def build_search_url(task: ScrapeTaskAssigned) -> str:
    query = quote_plus(_build_bringo_search_text(task))
    return BRINGO_SEARCH_API.format(query=query) + f"?key={BRINGO_API_KEY}&num_results_Products=24"


async def scrape(task: ScrapeTaskAssigned, *, timeout: float = 15.0) -> list[RawProduct]:
    url = build_search_url(task)
    payload, page_url = await _fetch_search_payload(url, timeout=timeout)
    return parse_products(payload, task, page_url=page_url)


async def _fetch_search_payload(url: str, *, timeout: float) -> tuple[str, str]:
    headers = {
        "User-Agent": BROWSER_USER_AGENT,
        "Accept-Language": "fr-MA,fr;q=0.9,en;q=0.8",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
        response = await client.get(url)
        response.raise_for_status()
    return response.text, url


def parse_products(payload: str, task: ScrapeTaskAssigned, *, page_url: str | None = None) -> list[RawProduct]:
    page_url = page_url or build_search_url(task)
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return []

    items = data.get("sections", {}).get("Products", [])
    products: list[RawProduct] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = clean_text(str(item.get("value") or ""))
        item_data = item.get("data") if isinstance(item.get("data"), dict) else {}
        price_cents = item_data.get("price")
        relative_url = clean_text(str(item_data.get("url") or ""))
        if not title or price_cents is None or not relative_url:
            continue
        price = _parse_price_cents(price_cents)
        url = _clean_product_url(f"{BRINGO_BASE_URL}{relative_url}")
        if price is None or not url:
            continue
        products.append(
            _raw_product(
                task,
                title=title,
                price=price,
                url=url,
                metadata={
                    "parser": "constructor_api",
                    "category": "grocery",
                    "product_id": str(item_data.get("id") or ""),
                },
            )
        )
    return _dedupe_and_filter(products, task)


def _parse_price_cents(value: object) -> float | None:
    try:
        cents = float(value)
    except (TypeError, ValueError):
        return None
    if cents <= 0:
        return None
    return round(cents / 100.0, 2)


def _raw_product(
    task: ScrapeTaskAssigned,
    *,
    title: str,
    price: float,
    url: str,
    metadata: dict[str, str],
    availability: Availability = Availability.IN_STOCK,
) -> RawProduct:
    return RawProduct(
        request_id=task.request_id,
        user_id=task.user_id,
        channel=task.channel,
        query=task.query,
        source="bringo",
        title=title,
        price=price,
        currency=task.query.currency,
        url=url,
        availability=availability,
        seller="Bringo Carrefour",
        rating=None,
        metadata=metadata,
    )


def _clean_product_url(url: str | None) -> str | None:
    if not url or "bringo.ma" not in url:
        return None
    cleaned = url.split("?", 1)[0].split("#", 1)[0]
    if "/products/" not in cleaned:
        return None
    return cleaned


def _dedupe_and_filter(products: list[RawProduct], task: ScrapeTaskAssigned) -> list[RawProduct]:
    seen: set[str] = set()
    filtered: list[RawProduct] = []
    for product in products:
        if product.price <= 0 or not _matches_query(product, task) or not budget_allows(product.price, task.query):
            continue
        key = f"{product.url}"
        if key in seen:
            continue
        seen.add(key)
        filtered.append(product)
    return filtered


def _build_bringo_search_text(task: ScrapeTaskAssigned) -> str:
    query = task.query
    product = PRODUCT_TERMS.get(query.product.lower(), query.product) if query.product else None
    parts = [query.brand, product, query.color]
    return " ".join(part for part in parts if part).strip() or build_search_text(task)


def _matches_query(product: RawProduct, task: ScrapeTaskAssigned) -> bool:
    searchable_text = clean_text(f"{product.title} {product.url}").lower()
    return (
        matches_brand(searchable_text, task.query)
        and matches_product(searchable_text, task.query, PRODUCT_MATCH_TERMS)
        and matches_color(searchable_text, task.query)
    )
