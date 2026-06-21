"""Avito scraper provider.

The parser is intentionally defensive because marketplace HTML changes often.
It supports JSON-LD product/listing data and generic card-like HTML blocks.
"""

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
    parse_mad_price,
)
from shared.events.schemas import Availability, RawProduct, ScrapeTaskAssigned

AVITO_BASE_URL = "https://www.avito.ma"
AVITO_SEARCH_URL = "https://www.avito.ma/fr/maroc/{query}"
CARD_RE = re.compile(
    r"<(?P<tag>article|div|li)\b(?P<attrs>[^>]*)>(?P<body>.*?)</(?P=tag)>",
    re.IGNORECASE | re.DOTALL,
)
HREF_RE = re.compile(r"href=[\"'](?P<href>[^\"']+)[\"']", re.IGNORECASE)
TITLE_ATTR_RE = re.compile(r"(?:aria-label|title)=[\"'](?P<title>[^\"']+)[\"']", re.IGNORECASE)
CARD_PRICE_RE = re.compile(r"(?P<amount>\d[\d\s.,]*)\s*(?:MAD|DH|DHS|درهم)", re.IGNORECASE)
SCRIPT_JSON_RE = re.compile(
    r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(?P<json>.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)


def build_search_url(task: ScrapeTaskAssigned) -> str:
    query = quote_plus(build_search_text(task))
    return AVITO_SEARCH_URL.format(query=query)


async def scrape(task: ScrapeTaskAssigned, *, timeout: float = 15.0) -> list[RawProduct]:
    url = build_search_url(task)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
        ),
        "Accept-Language": "fr-MA,fr;q=0.9,en;q=0.8",
    }
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
        response = await client.get(url)
        response.raise_for_status()
    return parse_products(response.text, task, page_url=str(response.url))


def parse_products(html: str, task: ScrapeTaskAssigned, *, page_url: str | None = None) -> list[RawProduct]:
    page_url = page_url or build_search_url(task)
    products = _parse_json_ld_products(html, task, page_url=page_url)
    products.extend(_parse_card_products(html, task, page_url=page_url))
    return _dedupe_and_filter(products, task)


def _parse_json_ld_products(html: str, task: ScrapeTaskAssigned, *, page_url: str) -> list[RawProduct]:
    products: list[RawProduct] = []
    for match in SCRIPT_JSON_RE.finditer(html):
        raw_json = clean_text(match.group("json"))
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError:
            continue
        for item in _walk_json(payload):
            if not isinstance(item, dict):
                continue
            item_type = item.get("@type") or item.get("type")
            if isinstance(item_type, list):
                item_type = " ".join(str(part) for part in item_type)
            if item_type and "product" not in str(item_type).lower() and "offer" not in str(item_type).lower():
                continue
            offers = item.get("offers") if isinstance(item.get("offers"), dict) else {}
            title = clean_text(str(item.get("name") or item.get("title") or ""))
            price_value = item.get("price") or offers.get("price")
            parsed_price = parse_mad_price(str(price_value)) if price_value is not None else None
            url = absolute_url(page_url, str(item.get("url") or offers.get("url") or ""))
            if title and parsed_price is not None and url:
                products.append(
                    _raw_product(
                        task,
                        title=title,
                        price=parsed_price,
                        url=url,
                        metadata={"parser": "json_ld"},
                    )
                )
    return products


def _parse_card_products(html: str, task: ScrapeTaskAssigned, *, page_url: str) -> list[RawProduct]:
    products: list[RawProduct] = []
    for match in CARD_RE.finditer(html):
        block = match.group(0)
        if "avito" not in block.lower() and "mad" not in block.lower() and "dh" not in block.lower():
            continue
        href_match = HREF_RE.search(block)
        href = href_match.group("href") if href_match else None
        url = absolute_url(page_url, href)
        if not url or "avito" not in url:
            continue
        price = _extract_card_price(block)
        if price is None:
            continue
        title = _extract_title(block)
        if not title:
            continue
        products.append(
            _raw_product(
                task,
                title=title,
                price=price,
                url=url,
                metadata={"parser": "html_card"},
            )
        )
    return products


def _extract_card_price(block: str) -> float | None:
    match = CARD_PRICE_RE.search(clean_text(block))
    return parse_mad_price(match.group(0)) if match else None


def _extract_title(block: str) -> str:
    attr_match = TITLE_ATTR_RE.search(block)
    if attr_match:
        title = clean_text(attr_match.group("title"))
        if title:
            return title
    headings = re.findall(r"<h[1-6][^>]*>(.*?)</h[1-6]>", block, flags=re.IGNORECASE | re.DOTALL)
    for heading in headings:
        title = clean_text(heading)
        if title:
            return title
    link_text = re.findall(r"<a[^>]*>(.*?)</a>", block, flags=re.IGNORECASE | re.DOTALL)
    for text in link_text:
        title = clean_text(text)
        if title and not parse_mad_price(title):
            return title
    return ""


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
        source="avito",
        title=title,
        price=price,
        currency=task.query.currency,
        url=url,
        availability=Availability.UNKNOWN,
        seller="Avito",
        rating=None,
        metadata=metadata,
    )


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
        if not budget_allows(product.price, task.query):
            continue
        key = f"{product.title.lower()}:{round(product.price)}:{product.url}"
        if key in seen:
            continue
        seen.add(key)
        filtered.append(product)
    return filtered
