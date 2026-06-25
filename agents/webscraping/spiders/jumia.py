"""Jumia.ma scraper provider."""

from __future__ import annotations

import json
import re
from urllib.parse import quote_plus

from agents.webscraping.spiders.base import (
    absolute_url,
    budget_allows,
    build_search_text,
    clean_text,
    matches_brand,
    matches_color,
    matches_product,
)
from agents.webscraping.tools.playwright_scraper import fetch_scrape_html
from shared.events.schemas import Availability, RawProduct, ScrapeTaskAssigned

JUMIA_BASE_URL = "https://www.jumia.ma"
JUMIA_SEARCH_URL = "https://www.jumia.ma/catalog/?q={query}"
JUMIA_PRODUCT_TERMS = {
    "phone": "smartphone",
    "telephone": "smartphone",
    "smartphone": "smartphone",
    "laptop": "ordinateur portable",
}
PHONE_ACCESSORY_TERMS = {
    "adaptateur",
    "cable",
    "câble",
    "chargeur",
    "coque",
    "ecouteur",
    "écouteur",
    "etui",
    "étui",
    "pochette",
    "support",
}
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
SCRIPT_JSON_RE = re.compile(
    r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(?P<json>.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)
PRICE_RE = re.compile(
    r"(?P<amount>\d{1,3}(?:[\s,.]\d{3})*(?:[,.]\d{2})?|\d+(?:[,.]\d{2})?)\s*(?:dh|dhs|mad|درهم)",
    re.IGNORECASE,
)


def build_search_url(task: ScrapeTaskAssigned) -> str:
    return JUMIA_SEARCH_URL.format(query=quote_plus(_build_jumia_search_text(task)))


async def scrape(task: ScrapeTaskAssigned, *, timeout: float = 15.0) -> list[RawProduct]:
    url = build_search_url(task)
    html, page_url = await _fetch_html(url, timeout=timeout)
    return parse_products(html, task, page_url=page_url)


async def _fetch_html(url: str, *, timeout: float) -> tuple[str, str]:
    return await fetch_scrape_html(url, timeout=timeout, locale="fr-MA")


def parse_products(html: str, task: ScrapeTaskAssigned, *, page_url: str | None = None) -> list[RawProduct]:
    page_url = page_url or build_search_url(task)
    products = _parse_json_ld_products(html, task, page_url=page_url)
    products.extend(_parse_dom_products(html, task, page_url=page_url))
    return _dedupe_and_filter(products, task)


def _parse_json_ld_products(html: str, task: ScrapeTaskAssigned, *, page_url: str) -> list[RawProduct]:
    products: list[RawProduct] = []
    for match in SCRIPT_JSON_RE.finditer(html):
        try:
            payload = json.loads(clean_text(match.group("json")))
        except json.JSONDecodeError:
            continue
        for item in _walk_json(payload):
            if not isinstance(item, dict):
                continue
            item_type = item.get("@type") or item.get("type")
            if isinstance(item_type, list):
                item_type = " ".join(str(part) for part in item_type)
            if item_type and "product" not in str(item_type).lower():
                continue
            offers = item.get("offers") if isinstance(item.get("offers"), dict) else {}
            title = clean_text(str(item.get("name") or item.get("title") or ""))
            price_value = item.get("price") or offers.get("price")
            price = _parse_price(str(price_value)) if price_value is not None else None
            url = absolute_url(page_url, str(item.get("url") or offers.get("url") or ""))
            if title and price is not None and url:
                products.append(_raw_product(task, title=title, price=price, url=url, metadata={"parser": "json_ld"}))
    return products


def _parse_dom_products(html: str, task: ScrapeTaskAssigned, *, page_url: str) -> list[RawProduct]:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []
    soup = BeautifulSoup(html, "html.parser")
    products: list[RawProduct] = []
    for card in soup.select("article.prd, article, div[data-sku], div.product-card"):
        link, url = _extract_product_link(card, page_url)
        if not url:
            continue
        block_text = clean_text(card.get_text(" ", strip=True))
        title = _extract_title(card, link, block_text)
        price = _extract_sale_price(block_text)
        rating = _extract_rating(block_text)
        if title and price is not None:
            products.append(
                _raw_product(
                    task,
                    title=title,
                    price=price,
                    url=url,
                    rating=rating,
                    metadata={"parser": "dom_card"},
                )
            )
    return products


def _extract_product_link(card, page_url: str):
    for link in card.select("a[href]"):
        url = _clean_product_url(absolute_url(page_url, link.get("href")))
        if url:
            return link, url
    return None, None


def _extract_title(card, link, block_text: str) -> str:
    title_node = card.select_one(".name, h3, h2")
    if title_node:
        title = clean_text(title_node.get_text(" ", strip=True))
        if title:
            return title
    if link is not None:
        for attr in ("aria-label", "title"):
            title = clean_text(link.get(attr))
            if title:
                return title
        title = clean_text(link.get_text(" ", strip=True))
        if title and _parse_price(title) is None:
            return title
    return clean_text(re.split(r"Prix|MAD|DH", block_text, maxsplit=1, flags=re.IGNORECASE)[0])


def _extract_sale_price(text: str) -> float | None:
    prices = [_parse_price(match.group(0)) for match in PRICE_RE.finditer(text)]
    prices = [price for price in prices if price is not None]
    return prices[0] if prices else None


def _parse_price(value: str | None) -> float | None:
    if not value:
        return None
    match = PRICE_RE.search(clean_text(value))
    raw_amount = match.group("amount") if match else clean_text(value)
    raw_amount = raw_amount.replace(" ", "")
    if "," in raw_amount and "." in raw_amount:
        normalized = raw_amount.replace(",", "") if raw_amount.rfind(",") < raw_amount.rfind(".") else raw_amount.replace(".", "").replace(",", ".")
    elif "," in raw_amount:
        parts = raw_amount.split(",")
        normalized = raw_amount.replace(",", "") if len(parts[-1]) == 3 else raw_amount.replace(",", ".")
    elif "." in raw_amount:
        parts = raw_amount.split(".")
        normalized = raw_amount.replace(".", "") if len(parts[-1]) == 3 else raw_amount
    else:
        normalized = raw_amount
    try:
        return float(normalized)
    except ValueError:
        return None


def _extract_rating(text: str) -> float | None:
    match = re.search(r"(?P<rating>\d(?:[,.]\d)?)\s*(?:sur|out of|/)\s*5", text, re.IGNORECASE)
    if not match:
        return None
    try:
        return float(match.group("rating").replace(",", "."))
    except ValueError:
        return None


def _raw_product(
    task: ScrapeTaskAssigned,
    *,
    title: str,
    price: float,
    url: str,
    metadata: dict[str, str],
    rating: float | None = None,
) -> RawProduct:
    return RawProduct(
        request_id=task.request_id,
        user_id=task.user_id,
        channel=task.channel,
        query=task.query,
        source="jumia",
        title=title,
        price=price,
        currency=task.query.currency,
        url=url,
        availability=Availability.UNKNOWN,
        seller="Jumia",
        rating=rating,
        metadata=metadata,
    )


def _clean_product_url(url: str | None) -> str | None:
    if not url or "jumia.ma" not in url:
        return None
    cleaned = url.split("?", 1)[0]
    blocked_paths = ("/customer/", "/cart/", "/checkout/", "/wishlist/")
    if any(path in cleaned for path in blocked_paths):
        return None
    if not cleaned.endswith(".html"):
        return None
    return cleaned


def _walk_json(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _dedupe_and_filter(products: list[RawProduct], task: ScrapeTaskAssigned) -> list[RawProduct]:
    seen: set[str] = set()
    filtered: list[RawProduct] = []
    for product in products:
        if product.price <= 0 or not _matches_query(product, task) or not budget_allows(product.price, task.query):
            continue
        key = f"{product.title.lower()}:{round(product.price)}:{product.url}"
        if key in seen:
            continue
        seen.add(key)
        filtered.append(product)
    return filtered


def _matches_query(product: RawProduct, task: ScrapeTaskAssigned) -> bool:
    query = task.query
    searchable_text = clean_text(f"{product.title} {product.url}").lower()
    if not matches_brand(searchable_text, query):
        return False
    if not matches_product(searchable_text, query):
        return False
    if not matches_color(searchable_text, query):
        return False
    if query.product and query.product.lower() in {"phone", "telephone", "smartphone"}:
        if any(term in searchable_text for term in PHONE_ACCESSORY_TERMS):
            return False
    return True


def _build_jumia_search_text(task: ScrapeTaskAssigned) -> str:
    query = task.query
    product = _localized_product_term(query.product)
    if query.brand and query.brand.lower() == "samsung" and product == "smartphone":
        product = "Galaxy"
    parts = [query.brand, product, query.color]
    return " ".join(part for part in parts if part).strip() or build_search_text(task)


def _localized_product_term(product: str | None) -> str | None:
    if not product:
        return None
    return JUMIA_PRODUCT_TERMS.get(product.lower(), product)
