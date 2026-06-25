"""Moteur.ma scraper provider for vehicle listings.

Moteur.ma is a vehicle marketplace, so this provider keeps the shared RawProduct
contract while storing vehicle-specific fields in metadata.
"""

from __future__ import annotations

import re
from urllib.parse import urlencode

from agents.webscraping.spiders.base import absolute_url, budget_allows, build_search_text, clean_text
from agents.webscraping.tools.playwright_scraper import fetch_scrape_html
from shared.events.schemas import Availability, RawProduct, ScrapeTaskAssigned

MOTEUR_BASE_URL = "https://www.moteur.ma"
MOTEUR_USED_CARS_URL = "https://www.moteur.ma/fr/voiture/achat-voiture-occasion/"
MOTEUR_USED_CARS_SEARCH_URL = "https://www.moteur.ma/fr/voiture/achat-voiture-occasion/recherche/"
PRICE_RE = re.compile(
    r"(?P<amount>\d{1,3}(?:[\s,.]\d{3})*(?:[,.]\d{2})?|\d+(?:[,.]\d{2})?)\s*(?:mad|dh|dhs|درهم)",
    re.IGNORECASE,
)
GENERIC_VEHICLE_TERMS = {"car", "cars", "vehicle", "voiture", "auto", "moto", "motorcycle", "camion", "truck"}


def build_search_url(task: ScrapeTaskAssigned) -> str:
    params: dict[str, str] = {}
    if task.query.budget is not None:
        params["prix_max"] = str(round(task.query.budget * 1.25))
    return MOTEUR_USED_CARS_SEARCH_URL + (f"?{urlencode(params)}" if params else "")


async def scrape(task: ScrapeTaskAssigned, *, timeout: float = 15.0) -> list[RawProduct]:
    url = build_search_url(task)
    html, page_url = await fetch_scrape_html(url, timeout=timeout, locale="fr-MA")
    return parse_products(html, task, page_url=page_url)


def parse_products(html: str, task: ScrapeTaskAssigned, *, page_url: str | None = None) -> list[RawProduct]:
    page_url = page_url or build_search_url(task)
    products = _parse_dom_products(html, task, page_url=page_url)
    return _dedupe_and_filter(products, task)


def _parse_dom_products(html: str, task: ScrapeTaskAssigned, *, page_url: str) -> list[RawProduct]:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    soup = BeautifulSoup(html, "html.parser")
    products: list[RawProduct] = []
    for card in soup.select(".ads-index-card"):
        link = card.select_one('a[href*="detail-annonce"]')
        url = absolute_url(page_url, link.get("href") if link else None)
        title = clean_text(_text_from_first(card, ".ads-index-title"))
        price = _parse_price(_text_from_first(card, ".ad-price-grid"))
        if not url or not title or price is None:
            continue
        metadata = _extract_metadata(card)
        products.append(_raw_product(task, title=title, price=price, url=url, metadata=metadata))
    return products


def _text_from_first(card, selector: str) -> str:
    node = card.select_one(selector)
    return node.get_text(" ", strip=True) if node else ""


def _extract_metadata(card) -> dict[str, str]:
    metadata = {"parser": "dom_card", "category": "vehicle", "vehicle_type": "car"}
    city_nodes = card.select(".item-card9-desc a")
    if city_nodes:
        city = clean_text(city_nodes[0].get_text(" ", strip=True))
        if city:
            metadata["city"] = city
    description = clean_text(_text_from_first(card, ".ad-desc"))
    if description:
        metadata["description"] = description

    meta_values = [clean_text(node.get_text(" ", strip=True)) for node in card.select(".ad-meta span")]
    meta_values = [value for value in meta_values if value]
    if len(meta_values) > 0:
        metadata["year"] = meta_values[0]
    if len(meta_values) > 1:
        metadata["transmission"] = meta_values[1]
    if len(meta_values) > 2:
        metadata["fuel"] = meta_values[2]
    if len(meta_values) > 3:
        metadata["mileage"] = meta_values[3]
    return metadata


def _parse_price(value: str | None) -> float | None:
    if not value:
        return None
    match = PRICE_RE.search(clean_text(value))
    if not match:
        return None
    amount = match.group("amount").replace(" ", "")
    if "," in amount and "." in amount:
        normalized = amount.replace(",", "") if amount.rfind(",") < amount.rfind(".") else amount.replace(".", "").replace(",", ".")
    elif "," in amount:
        parts = amount.split(",")
        normalized = amount.replace(",", "") if len(parts[-1]) == 3 else amount.replace(",", ".")
    elif "." in amount:
        parts = amount.split(".")
        normalized = amount.replace(".", "") if len(parts[-1]) == 3 else amount
    else:
        normalized = amount
    try:
        return float(normalized)
    except ValueError:
        return None


def _raw_product(
    task: ScrapeTaskAssigned,
    *,
    title: str,
    price: float,
    url: str,
    metadata: dict[str, str],
) -> RawProduct:
    return RawProduct(
        request_id=task.request_id,
        user_id=task.user_id,
        channel=task.channel,
        query=task.query,
        source="moteur",
        title=title,
        price=price,
        currency=task.query.currency,
        url=url,
        availability=Availability.UNKNOWN,
        seller="Moteur.ma",
        rating=None,
        metadata=metadata,
    )


def _dedupe_and_filter(products: list[RawProduct], task: ScrapeTaskAssigned) -> list[RawProduct]:
    seen: set[str] = set()
    filtered: list[RawProduct] = []
    for product in products:
        if product.price <= 0:
            continue
        if not _matches_query(product, task):
            continue
        if not budget_allows(product.price, task.query):
            continue
        key = f"{product.title.lower()}:{round(product.price)}:{product.url}"
        if key in seen:
            continue
        seen.add(key)
        filtered.append(product)
    return filtered


def _matches_query(product: RawProduct, task: ScrapeTaskAssigned) -> bool:
    query = task.query
    searchable_text = clean_text(
        f"{product.title} {product.url} {product.metadata.get('description', '')} {product.metadata.get('city', '')}"
    ).lower()
    if query.brand and query.brand.lower() not in searchable_text:
        return False
    if query.product and query.product.lower() not in GENERIC_VEHICLE_TERMS:
        if query.product.lower() not in searchable_text:
            return False
    if query.city and query.city.lower() not in searchable_text:
        return False
    return True