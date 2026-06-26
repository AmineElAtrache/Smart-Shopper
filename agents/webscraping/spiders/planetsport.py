"""Planet Sport (planetsport.ma) scraper provider."""

from __future__ import annotations

import json
import re
from urllib.parse import quote_plus

import httpx

from agents.webscraping.spiders.base import (
    absolute_url,
    budget_allows,
    build_search_text,
    clean_text,
    matches_brand,
    matches_color,
    matches_product,
)
from shared.events.schemas import Availability, RawProduct, ScrapeTaskAssigned

PLANETSPORT_BASE_URL = "https://planetsport.ma"
PLANETSPORT_SEARCH_URL = (
    "https://planetsport.ma/recherche?controller=search&s={query}"
)
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
PRODUCT_TERMS = {
    "shoes": "chaussures",
    "shoe": "chaussures",
    "sneakers": "baskets",
    "bike": "velo",
    "bicycle": "velo",
    "football": "football",
    "treadmill": "tapis de course",
    "dumbbell": "halteres",
}
PRODUCT_MATCH_TERMS = {
    "shoes": {"shoes", "shoe", "chaussures", "baskets", "sneakers"},
    "shoe": {"shoe", "shoes", "chaussures", "baskets"},
    "sneakers": {"sneakers", "baskets", "chaussures"},
    "bike": {"bike", "bicycle", "velo", "vélo"},
    "bicycle": {"bicycle", "bike", "velo", "vélo"},
    "football": {"football", "ballon", "maillot"},
    "treadmill": {"treadmill", "tapis"},
    "dumbbell": {"dumbbell", "haltere", "haltère"},
}
DATALAYER_RE = re.compile(
    r"cdcDatalayer\s*=\s*(?P<json>\{.*?\});\s*\n?\s*dataLayer\.push",
    re.DOTALL,
)
PRICE_RE = re.compile(
    r"(?P<amount>\d{1,3}(?:[\s,.]\d{3})*(?:[,.]\d{2})?|\d+(?:[,.]\d{2})?)\s*(?:MAD|DH|DHS|dh|dhs|mad)",
    re.IGNORECASE,
)


def build_search_url(task: ScrapeTaskAssigned) -> str:
    return PLANETSPORT_SEARCH_URL.format(
        query=quote_plus(_build_planetsport_search_text(task))
    )


async def scrape(task: ScrapeTaskAssigned, *, timeout: float = 15.0) -> list[RawProduct]:
    url = build_search_url(task)
    html, page_url = await _fetch_html_with_httpx(url, timeout=timeout)
    return parse_products(html, task, page_url=page_url)


async def _fetch_html_with_httpx(url: str, *, timeout: float) -> tuple[str, str]:
    headers = {
        "User-Agent": BROWSER_USER_AGENT,
        "Accept-Language": "fr-MA,fr;q=0.9,en;q=0.8",
    }
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
        response = await client.get(url)
        response.raise_for_status()
    return response.text, str(response.url)


def parse_products(html: str, task: ScrapeTaskAssigned, *, page_url: str | None = None) -> list[RawProduct]:
    page_url = page_url or build_search_url(task)
    products = _parse_datalayer_products(html, task, page_url=page_url)
    products.extend(_parse_dom_products(html, task, page_url=page_url))
    return _dedupe_and_filter(products, task)


def _parse_datalayer_products(html: str, task: ScrapeTaskAssigned, *, page_url: str) -> list[RawProduct]:
    match = DATALAYER_RE.search(html)
    if not match:
        return []
    try:
        payload = json.loads(match.group("json"))
    except json.JSONDecodeError:
        return []

    items = payload.get("ecommerce", {}).get("items", [])
    products: list[RawProduct] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = clean_text(str(item.get("item_name") or ""))
        price_raw = item.get("price_tax_inc") or item.get("price")
        price = _parse_price(str(price_raw)) if price_raw is not None else None
        item_id = clean_text(str(item.get("item_id") or ""))
        if not title or price is None or not item_id:
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        url = f"{PLANETSPORT_BASE_URL}/search?s={quote_plus(title)}#{item_id}"
        products.append(
            _raw_product(
                task,
                title=title,
                price=price,
                url=url,
                metadata={"parser": "datalayer", "category": "sports", "item_id": item_id},
            )
        )
    return products


def _parse_dom_products(html: str, task: ScrapeTaskAssigned, *, page_url: str) -> list[RawProduct]:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    soup = BeautifulSoup(html, "html.parser")
    products: list[RawProduct] = []
    for article in soup.select("article.product-miniature"):
        title_node = article.select_one("h3.product-title a, .product-title a")
        if title_node is None:
            continue
        title = clean_text(title_node.get_text(" ", strip=True))
        url = _clean_product_url(absolute_url(page_url, title_node.get("href")))
        if not title or not url:
            continue
        block_text = clean_text(article.get_text(" ", strip=True))
        price = _extract_sale_price(block_text)
        if price is None:
            continue
        availability = (
            Availability.IN_STOCK
            if re.search(r"en stock|disponible|au panier", block_text, re.IGNORECASE)
            else Availability.UNKNOWN
        )
        products.append(
            _raw_product(
                task,
                title=title,
                price=price,
                url=url,
                availability=availability,
                metadata={"parser": "dom_card", "category": "sports"},
            )
        )
    return products


def _extract_sale_price(text: str) -> float | None:
    prices = [_parse_price(match.group(0)) for match in PRICE_RE.finditer(text)]
    prices = [price for price in prices if price is not None]
    return prices[0] if prices else None


def _parse_price(value: str | None) -> float | None:
    if not value:
        return None
    match = PRICE_RE.search(clean_text(value))
    raw_amount = match.group("amount") if match else clean_text(value)
    raw_amount = raw_amount.replace("\xa0", " ").replace(" ", "")
    if "," in raw_amount and "." in raw_amount:
        normalized = (
            raw_amount.replace(",", "")
            if raw_amount.rfind(",") < raw_amount.rfind(".")
            else raw_amount.replace(".", "").replace(",", ".")
        )
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


def _raw_product(
    task: ScrapeTaskAssigned,
    *,
    title: str,
    price: float,
    url: str,
    metadata: dict[str, str],
    availability: Availability = Availability.UNKNOWN,
) -> RawProduct:
    return RawProduct(
        request_id=task.request_id,
        user_id=task.user_id,
        channel=task.channel,
        query=task.query,
        source="planetsport",
        title=title,
        price=price,
        currency=task.query.currency,
        url=url,
        availability=availability,
        seller="Planet Sport",
        rating=None,
        metadata=metadata,
    )


def _clean_product_url(url: str | None) -> str | None:
    if not url or "planetsport.ma" not in url:
        return None
    cleaned = url.split("#", 1)[0].split("?", 1)[0]
    if any(token in cleaned for token in ("/panier", "/mon-compte", "/search")):
        return None
    if not re.search(r"/\d+-", cleaned):
        return None
    return cleaned


def _dedupe_and_filter(products: list[RawProduct], task: ScrapeTaskAssigned) -> list[RawProduct]:
    seen: set[str] = set()
    filtered: list[RawProduct] = []
    for product in products:
        if product.price <= 0 or not _matches_query(product, task) or not budget_allows(product.price, task.query):
            continue
        key = f"{round(product.price)}:{product.url}"
        if key in seen:
            continue
        seen.add(key)
        filtered.append(product)
    return filtered


def _build_planetsport_search_text(task: ScrapeTaskAssigned) -> str:
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
