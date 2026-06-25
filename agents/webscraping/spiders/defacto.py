"""DeFacto Morocco scraper provider."""

from __future__ import annotations

import json
import re
from urllib.parse import quote_plus

from agents.webscraping.spiders.base import absolute_url, budget_allows, build_search_text, clean_text
from agents.webscraping.tools.playwright_scraper import fetch_scrape_html
from shared.events.schemas import Availability, RawProduct, ScrapeTaskAssigned

DEFACTO_BASE_URL = "https://www.defacto.com"
DEFACTO_SEARCH_URL = "https://www.defacto.com/fr-ma/search?q={query}"
DEFACTO_PRODUCT_TERMS = {
    "shirt": "chemise",
    "t-shirt": "t-shirt",
    "tshirt": "t-shirt",
    "pants": "pantalon",
    "jeans": "jean",
    "jacket": "veste",
    "dress": "robe",
    "shoes": "chaussures",
}
DEFACTO_COLOR_TERMS = {
    "black": "noir",
    "white": "blanc",
    "blue": "bleu",
    "red": "rouge",
    "green": "vert",
    "gray": "gris",
    "grey": "gris",
    "brown": "marron",
}
DEFACTO_COLOR_ALIASES = {
    "black": {"black", "noir", "siyah"},
    "white": {"white", "blanc", "beyaz"},
    "blue": {"blue", "bleu", "mavi"},
    "red": {"red", "rouge", "kirmizi", "kırmızı"},
    "green": {"green", "vert", "yesil", "yeşil"},
    "gray": {"gray", "grey", "gris", "gri"},
    "grey": {"gray", "grey", "gris", "gri"},
    "brown": {"brown", "marron", "kahverengi"},
}
SCRIPT_JSON_RE = re.compile(
    r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(?P<json>.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)
PRICE_RE = re.compile(
    r"(?P<amount>\d{1,3}(?:[\s,.]\d{3})*(?:[,.]\d{2})?|\d+(?:[,.]\d{2})?)\s*(?:dh|dhs|mad|درهم|€|eur)?",
    re.IGNORECASE,
)


def build_search_url(task: ScrapeTaskAssigned) -> str:
    return DEFACTO_SEARCH_URL.format(query=quote_plus(_build_defacto_search_text(task)))


async def scrape(task: ScrapeTaskAssigned, *, timeout: float = 15.0) -> list[RawProduct]:
    url = build_search_url(task)
    html, page_url = await _fetch_html(url, timeout=timeout)
    return parse_products(html, task, page_url=page_url)


async def _fetch_html(url: str, *, timeout: float) -> tuple[str, str]:
    return await fetch_scrape_html(url, timeout=timeout, locale="en-MA")


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
                products.append(
                    _raw_product(task, title=title, price=price, url=url, metadata={"parser": "json_ld", "category": "fashion"})
                )
    return products


def _parse_dom_products(html: str, task: ScrapeTaskAssigned, *, page_url: str) -> list[RawProduct]:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []
    soup = BeautifulSoup(html, "html.parser")
    products: list[RawProduct] = []
    for anchor in soup.select("a[href]"):
        url = _clean_product_url(absolute_url(page_url, anchor.get("href")))
        if not url:
            continue
        block = _nearest_product_block(anchor)
        block_text = clean_text(block.get_text(" ", strip=True) if block else anchor.get_text(" "))
        title = _extract_title(anchor, block_text)
        price = _extract_data_price(anchor) or _extract_sale_price(block_text)
        availability = Availability.OUT_OF_STOCK if re.search(r"out of stock|sold out", block_text, re.IGNORECASE) else Availability.UNKNOWN
        if title and price is not None:
            products.append(
                _raw_product(
                    task,
                    title=title,
                    price=price,
                    url=url,
                    availability=availability,
                    metadata={
                        "parser": "dom_card",
                        "category": "fashion",
                        "variant": clean_text(anchor.get("data-variant")),
                    },
                )
            )
    return products


def _nearest_product_block(anchor):
    current = anchor
    for _ in range(6):
        if current is None:
            return None
        if _extract_sale_price(clean_text(current.get_text(" ", strip=True))) is not None:
            return current
        current = current.parent
    return anchor.parent


def _extract_sale_price(text: str) -> float | None:
    sale_match = re.search(r"(?:sale|price|now)\s+(?P<price>[^\n]+?)(?:\s+regular|\s+old|$)", text, re.IGNORECASE)
    if sale_match:
        price = _parse_price(sale_match.group("price"))
        if price is not None:
            return price
    prices = [_parse_price(match.group(0)) for match in PRICE_RE.finditer(text)]
    prices = [price for price in prices if price is not None]
    return prices[0] if prices else None


def _extract_data_price(anchor) -> float | None:
    for attr in ("data-sale-price", "data-price", "data-discounted-price"):
        price = _parse_price(anchor.get(attr))
        if price is not None:
            return price
    return None


def _parse_price(value: str | None) -> float | None:
    if not value:
        return None
    match = PRICE_RE.search(clean_text(value))
    if not match:
        return None
    raw_amount = match.group("amount").replace(" ", "")
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


def _extract_title(anchor, block_text: str) -> str:
    data_title = clean_text(anchor.get("data-name"))
    if data_title:
        return data_title
    for attr in ("aria-label", "title"):
        title = clean_text(anchor.get(attr))
        if title:
            return title
    title = clean_text(anchor.get_text(" ", strip=True))
    if title and _parse_price(title) is None:
        return title
    title = clean_text(re.split(r"Sale|Price|MAD|DH|€", block_text, maxsplit=1, flags=re.IGNORECASE)[0])
    return title


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
        source="defacto",
        title=title,
        price=price,
        currency=task.query.currency,
        url=url,
        availability=availability,
        seller="DeFacto",
        rating=None,
        metadata=metadata,
    )


def _clean_product_url(url: str | None) -> str | None:
    if not url or "defacto.com" not in url:
        return None
    return url.split("?", 1)[0]


def _build_defacto_search_text(task: ScrapeTaskAssigned) -> str:
    query = task.query
    product = _localized_term(query.product, DEFACTO_PRODUCT_TERMS)
    color = _localized_term(query.color, DEFACTO_COLOR_TERMS)
    parts = [query.brand, product, color]
    return " ".join(part for part in parts if part).strip() or build_search_text(task)


def _localized_term(value: str | None, mapping: dict[str, str]) -> str | None:
    if not value:
        return None
    return mapping.get(value.lower(), value)


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
    metadata_text = " ".join(str(value) for value in product.metadata.values())
    searchable_text = clean_text(f"{product.title} {product.url} {metadata_text}").lower()
    if query.brand and query.brand.lower() not in searchable_text:
        return False
    if query.product and not _has_query_term(searchable_text, query.product, DEFACTO_PRODUCT_TERMS):
        return False
    if query.color and not _has_query_term(searchable_text, query.color, DEFACTO_COLOR_TERMS):
        return False
    return True


def _has_query_term(searchable_text: str, value: str, mapping: dict[str, str]) -> bool:
    terms = {value.lower(), mapping.get(value.lower(), value).lower()}
    terms.update(DEFACTO_COLOR_ALIASES.get(value.lower(), set()))
    return any(term in searchable_text for term in terms)
