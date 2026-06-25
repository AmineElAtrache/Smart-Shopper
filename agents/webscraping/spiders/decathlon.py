"""Decathlon.ma scraper provider."""

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
from agents.webscraping.tools.playwright_scraper import fetch_rendered_html
from shared.events.schemas import Availability, RawProduct, ScrapeTaskAssigned

DECATHLON_BASE_URL = "https://www.decathlon.ma"
DECATHLON_SEARCH_URL = "https://www.decathlon.ma/search?query={query}"
DECATHLON_SHOES_URL = "https://www.decathlon.ma/4976-chaussures-et-baskets"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
PRODUCT_TERMS = {
    "shoes": "chaussures",
    "shoe": "chaussures",
    "bike": "velo",
    "bicycle": "velo",
    "tent": "tente",
    "shirt": "t-shirt",
}
PRODUCT_MATCH_TERMS = {
    "shoes": {"shoes", "chaussures", "baskets"},
    "shoe": {"shoe", "chaussures", "baskets"},
    "bike": {"bike", "velo", "vélo"},
    "bicycle": {"bicycle", "velo", "vélo"},
    "tent": {"tent", "tente"},
    "shirt": {"shirt", "t-shirt", "tee-shirt"},
}
SCRIPT_JSON_RE = re.compile(
    r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(?P<json>.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)
PRICE_RE = re.compile(
    r"(?P<amount>\d{1,3}(?:[\s,.]\d{3})*(?:[,.]\d{2})?|\d+(?:[,.]\d{2})?)\s*(?:dh|dhs|mad|درهم)",
    re.IGNORECASE,
)


def build_search_url(task: ScrapeTaskAssigned) -> str:
    if (task.query.product or "").lower() in {"shoe", "shoes", "chaussures", "basket", "baskets"}:
        return DECATHLON_SHOES_URL
    return DECATHLON_SEARCH_URL.format(query=quote_plus(_build_decathlon_search_text(task)))


async def scrape(task: ScrapeTaskAssigned, *, timeout: float = 15.0) -> list[RawProduct]:
    url = build_search_url(task)
    html, page_url = await _fetch_html(url, timeout=timeout)
    return parse_products(html, task, page_url=page_url)


async def _fetch_html(url: str, *, timeout: float) -> tuple[str, str]:
    try:
        return await _fetch_html_with_httpx(url, timeout=timeout)
    except Exception:
        return await fetch_rendered_html(url, timeout=timeout, locale="fr-MA")


async def _fetch_html_with_httpx(url: str, *, timeout: float) -> tuple[str, str]:
    headers = {"User-Agent": BROWSER_USER_AGENT, "Accept-Language": "fr-MA,fr;q=0.9,en;q=0.8"}
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
        response = await client.get(url)
        response.raise_for_status()
    return response.text, str(response.url)


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
            url = _clean_product_url(absolute_url(page_url, str(item.get("url") or offers.get("url") or "")))
            if title and price is not None and url:
                products.append(_raw_product(task, title=title, price=price, url=url, metadata={"parser": "json_ld", "category": "sports"}))
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
        price = _extract_sale_price(block_text)
        availability = Availability.IN_STOCK if re.search(r"en stock|disponible", block_text, re.IGNORECASE) else Availability.UNKNOWN
        if title and price is not None:
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


def _extract_title(anchor, block_text: str) -> str:
    for attr in ("aria-label", "title", "data-name"):
        title = clean_text(anchor.get(attr))
        if title:
            return title
    title = clean_text(anchor.get_text(" ", strip=True))
    if title and _parse_price(title) is None:
        return title
    return _title_before_price_or_rating(block_text)


def _title_before_price_or_rating(text: str) -> str:
    title = clean_text(re.split(r"\d(?:[,.]\d)?\s+out of 5|Prix|MAD|DH", text, maxsplit=1, flags=re.IGNORECASE)[0])
    title = re.sub(r"^(Nouveauté|Dernière chance|Promotion)\s+", "", title, flags=re.IGNORECASE).strip()
    title = re.sub(r"^DECATHLON\s+", "", title, flags=re.IGNORECASE).strip()
    title = re.sub(r"\s+\d(?:[,.]\d)?$", "", title).strip()
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
        source="decathlon",
        title=title,
        price=price,
        currency=task.query.currency,
        url=url,
        availability=availability,
        seller="Decathlon",
        rating=None,
        metadata=metadata,
    )


def _clean_product_url(url: str | None) -> str | None:
    if not url or "decathlon.ma" not in url:
        return None
    cleaned = url.split("?", 1)[0]
    if "/p/" not in cleaned:
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
        key = f"{round(product.price)}:{product.url}"
        if key in seen:
            continue
        seen.add(key)
        filtered.append(product)
    return filtered


def _build_decathlon_search_text(task: ScrapeTaskAssigned) -> str:
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
