"""Mafiawaystore scraper provider.

Mafiawaystore is a Shopify-style Moroccan fashion store. Search pages expose
product handles and each product has a stable ``/products/{handle}.js`` JSON
endpoint, which is more reliable than theme CSS classes.
"""

from __future__ import annotations

import re
from urllib.parse import quote_plus

import httpx

from agents.webscraping.spiders.base import absolute_url, budget_allows, build_search_text, clean_text
from agents.webscraping.tools.playwright_scraper import fetch_scrape_html
from shared.events.schemas import Availability, RawProduct, ScrapeTaskAssigned

MAFIAWAY_BASE_URL = "https://mafiawaystore.com"
MAFIAWAY_SEARCH_URL = "https://mafiawaystore.com/search?q={query}"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
PRODUCT_HANDLE_RE = re.compile(r"/products/(?P<handle>[^\"'?#\s]+)", re.IGNORECASE)
PRICE_RE = re.compile(
    r"(?P<amount>\d{1,3}(?:[\s,.]\d{3})*(?:[,.]\d{2})?|\d+(?:[,.]\d{2})?)\s*(?:dh|dhs|mad|درهم)",
    re.IGNORECASE,
)


def build_search_url(task: ScrapeTaskAssigned) -> str:
    return MAFIAWAY_SEARCH_URL.format(query=quote_plus(build_search_text(task)))


async def scrape(task: ScrapeTaskAssigned, *, timeout: float = 15.0) -> list[RawProduct]:
    url = build_search_url(task)
    html, _page_url = await fetch_scrape_html(url, timeout=timeout, locale="fr-MA")
    handles = _extract_product_handles(html)
    headers = {
        "User-Agent": BROWSER_USER_AGENT,
        "Accept-Language": "fr-MA,fr;q=0.9,en;q=0.8",
    }
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
        products: list[RawProduct] = []
        for handle in handles[:20]:
            product = await _scrape_product_json(client, handle, task)
            if product is not None:
                products.append(product)
    return _dedupe_and_filter(products, task)


def parse_products(html: str, task: ScrapeTaskAssigned, *, page_url: str | None = None) -> list[RawProduct]:
    page_url = page_url or build_search_url(task)
    products = _parse_dom_products(html, task, page_url=page_url)
    return _dedupe_and_filter(products, task)


async def _scrape_product_json(
    client: httpx.AsyncClient,
    handle: str,
    task: ScrapeTaskAssigned,
) -> RawProduct | None:
    response = await client.get(f"{MAFIAWAY_BASE_URL}/products/{handle}.js")
    if response.status_code != 200:
        return None
    payload = response.json()
    title = clean_text(payload.get("title"))
    price = _price_from_cents(payload.get("price"))
    url = f"{MAFIAWAY_BASE_URL}/products/{payload.get('handle') or handle}"
    if not title or price is None:
        return None
    availability = Availability.IN_STOCK if payload.get("available") else Availability.UNKNOWN
    metadata = {
        "parser": "shopify_json",
        "category": "fashion",
        "handle": str(payload.get("handle") or handle),
    }
    variants = payload.get("variants")
    if isinstance(variants, list):
        available_variants = [str(v.get("title")) for v in variants if v.get("available")]
        if available_variants:
            metadata["available_variants"] = ", ".join(available_variants[:8])
    return _raw_product(
        task,
        title=title,
        price=price,
        url=url,
        availability=availability,
        metadata=metadata,
    )


def _parse_dom_products(html: str, task: ScrapeTaskAssigned, *, page_url: str) -> list[RawProduct]:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    soup = BeautifulSoup(html, "html.parser")
    products: list[RawProduct] = []
    for anchor in soup.select('a[href*="/products/"]'):
        url = _clean_product_url(absolute_url(page_url, anchor.get("href")))
        if not url:
            continue
        block = _nearest_product_block(anchor)
        block_text = clean_text(block.get_text(" ", strip=True) if block else anchor.get_text(" "))
        title = _extract_title(anchor, block_text)
        price = _extract_sale_price(block_text)
        if title and price is not None:
            products.append(
                _raw_product(
                    task,
                    title=title,
                    price=price,
                    url=url,
                    availability=Availability.UNKNOWN,
                    metadata={"parser": "dom_card", "category": "fashion"},
                )
            )
    return products


def _nearest_product_block(anchor):
    current = anchor
    for _ in range(5):
        if current is None:
            return None
        text = clean_text(current.get_text(" ", strip=True))
        if _extract_sale_price(text) is not None:
            return current
        current = current.parent
    return anchor.parent


def _extract_product_handles(html: str) -> list[str]:
    seen: set[str] = set()
    handles: list[str] = []
    for match in PRODUCT_HANDLE_RE.finditer(html):
        handle = match.group("handle")
        if handle in seen:
            continue
        seen.add(handle)
        handles.append(handle)
    return handles


def _extract_sale_price(text: str) -> float | None:
    reduced_match = re.search(r"Prix réduit\s+(?P<price>[^\n]+?)(?:\s+|$)", text, re.IGNORECASE)
    if reduced_match:
        price = _parse_price(reduced_match.group("price"))
        if price is not None:
            return price
    prices = [_parse_price(match.group(0)) for match in PRICE_RE.finditer(text)]
    prices = [price for price in prices if price is not None]
    return prices[-1] if prices else None


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


def _price_from_cents(value) -> float | None:
    try:
        return float(value) / 100
    except (TypeError, ValueError):
        return None


def _extract_title(anchor, block_text: str) -> str:
    for attr in ("aria-label", "title"):
        title = clean_text(anchor.get(attr))
        if title:
            return title
    title = clean_text(anchor.get_text(" ", strip=True))
    if title and _parse_price(title) is None:
        return title
    if "Prix" in block_text:
        title = re.split(r"Prix (?:régulier|reduit|réduit|final)", block_text, maxsplit=1, flags=re.IGNORECASE)[0]
        title = re.sub(r"^(Vue rapide\s+)?", "", clean_text(title), flags=re.IGNORECASE)
        if title:
            return title
    return ""


def _raw_product(
    task: ScrapeTaskAssigned,
    *,
    title: str,
    price: float,
    url: str,
    availability: Availability,
    metadata: dict[str, str],
) -> RawProduct:
    return RawProduct(
        request_id=task.request_id,
        user_id=task.user_id,
        channel=task.channel,
        query=task.query,
        source="mafiawaystore",
        title=title,
        price=price,
        currency=task.query.currency,
        url=url,
        availability=availability,
        seller="Mafiaway Store",
        rating=None,
        metadata=metadata,
    )


def _clean_product_url(url: str | None) -> str | None:
    if not url or "mafiawaystore.com" not in url:
        return None
    return url.split("?", 1)[0]


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
    searchable_text = clean_text(f"{product.title} {product.url}").lower()
    if query.brand and query.brand.lower() not in searchable_text:
        return False
    if query.product and query.product.lower() not in searchable_text:
        return False
    if query.color and query.color.lower() not in searchable_text:
        return False
    return True