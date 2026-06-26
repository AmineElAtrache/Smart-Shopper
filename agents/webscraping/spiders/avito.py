"""Avito scraper provider.

The parser is intentionally defensive because marketplace HTML changes often.
It supports browser-rendered pages, JSON-LD data, and generic card-like HTML blocks.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import quote, quote_plus

import httpx

from agents.webscraping.spiders.base import (
    absolute_url,
    budget_allows,
    build_search_text,
    clean_text,
    parse_mad_price,
    use_playwright_provider,
)
from shared.events.schemas import Availability, RawProduct, ScrapeTaskAssigned

AVITO_SEARCH_URL = "https://www.avito.ma/fr/{city}/{query}"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
AVITO_PRODUCT_TERMS = {
    "phone": "telephone",
    "smartphone": "telephone",
    "telephone": "telephone",
    "laptop": "pc portable",
    "tablet": "tablette",
    "headphones": "casque",
}
AVITO_COLOR_TERMS = {
    "black": "noir",
    "white": "blanc",
    "blue": "bleu",
    "red": "rouge",
    "green": "vert",
    "gray": "gris",
    "grey": "gris",
    "gold": "or",
    "silver": "argent",
}
PRODUCT_RELEVANCE_TERMS = {
    "phone": {"phone", "telephone", "telephones", "tÃ©lÃ©phone", "tÃ©lÃ©phones", "smartphone", "galaxy"},
    "smartphone": {"phone", "telephone", "telephones", "tÃ©lÃ©phone", "tÃ©lÃ©phones", "smartphone", "galaxy"},
    "telephone": {"phone", "telephone", "telephones", "tÃ©lÃ©phone", "tÃ©lÃ©phones", "smartphone", "galaxy"},
    "laptop": {"laptop", "pc", "ordinateur", "portable"},
    "tablet": {"tablet", "tablette", "ipad"},
    "headphones": {"headphones", "casque", "ecouteurs", "Ã©couteurs"},
}
CARD_RE = re.compile(
    r"<(?P<tag>article|div|li)\b(?P<attrs>[^>]*)>(?P<body>.*?)</(?P=tag)>",
    re.IGNORECASE | re.DOTALL,
)
HREF_RE = re.compile(r"href=[\"'](?P<href>[^\"']+)[\"']", re.IGNORECASE)
TITLE_ATTR_RE = re.compile(r"(?:aria-label|title)=[\"'](?P<title>[^\"']+)[\"']", re.IGNORECASE)
CARD_PRICE_RE = re.compile(r"(?P<amount>\d[\d\s.,]*)\s*(?:MAD|DH|DHS|Ø¯Ø±Ù‡Ù…)", re.IGNORECASE)
SCRIPT_JSON_RE = re.compile(
    r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(?P<json>.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)


def build_search_url(task: ScrapeTaskAssigned) -> str:
    city = _city_path_segment(task)
    query = quote_plus(_build_avito_search_text(task))
    return AVITO_SEARCH_URL.format(city=city, query=query)


async def scrape(task: ScrapeTaskAssigned, *, timeout: float = 15.0) -> list[RawProduct]:
    url = build_search_url(task)
    html, page_url = await _fetch_html(url, timeout=timeout)
    return parse_products(html, task, page_url=page_url)


async def _fetch_html(url: str, *, timeout: float) -> tuple[str, str]:
    if use_playwright_provider("avito"):
        return await _fetch_html_with_playwright(url, timeout=timeout)
    return await _fetch_html_with_httpx(url, timeout=timeout)


async def _fetch_html_with_playwright(url: str, *, timeout: float) -> tuple[str, str]:
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await _launch_browser(playwright)
        try:
            page = await browser.new_page(
                user_agent=BROWSER_USER_AGENT,
                locale="fr-MA",
                viewport={"width": 1366, "height": 900},
            )
            await page.goto(url, wait_until="domcontentloaded", timeout=int(timeout * 1000))
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except PlaywrightTimeoutError:
                pass
            try:
                await page.wait_for_selector("a[href]", timeout=7000)
            except PlaywrightTimeoutError:
                pass
            return await page.content(), page.url
        finally:
            await browser.close()


async def _launch_browser(playwright):
    try:
        return await playwright.chromium.launch(headless=True)
    except Exception as first_error:
        for executable_path in _local_browser_paths():
            try:
                return await playwright.chromium.launch(
                    headless=True,
                    executable_path=str(executable_path),
                )
            except Exception:
                continue
        raise first_error


def _local_browser_paths() -> list[Path]:
    return [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    ]


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
    products = _parse_json_ld_products(html, task, page_url=page_url)
    products.extend(_parse_dom_products(html, task, page_url=page_url))
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
                    _raw_product(task, title=title, price=parsed_price, url=url, metadata={"parser": "json_ld"})
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
        url = absolute_url(page_url, anchor.get("href"))
        if not url or "avito.ma" not in url or url.rstrip("/") == page_url.rstrip("/"):
            continue
        block = _nearest_price_block(anchor)
        if block is None:
            continue
        block_html = str(block)
        price = _extract_card_price(block_html)
        if price is None:
            continue
        title = _extract_title(block_html) or clean_text(anchor.get_text(" "))
        if not title:
            continue
        products.append(
            _raw_product(task, title=title, price=price, url=url, metadata={"parser": "dom_card"})
        )
    return products


def _nearest_price_block(node):
    current = node
    for _ in range(5):
        if current is None:
            return None
        if _extract_card_price(str(current)) is not None:
            return current
        current = current.parent
    return None


def _parse_card_products(html: str, task: ScrapeTaskAssigned, *, page_url: str) -> list[RawProduct]:
    products: list[RawProduct] = []
    for match in CARD_RE.finditer(html):
        block = match.group(0)
        if "avito" not in block.lower() and "mad" not in block.lower() and "dh" not in block.lower():
            continue
        href_match = HREF_RE.search(block)
        url = absolute_url(page_url, href_match.group("href") if href_match else None)
        if not url or "avito" not in url:
            continue
        price = _extract_card_price(block)
        title = _extract_title(block)
        if price is not None and title:
            products.append(
                _raw_product(task, title=title, price=price, url=url, metadata={"parser": "html_card"})
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


def _build_avito_search_text(task: ScrapeTaskAssigned) -> str:
    query = task.query
    product = _localized_product_term(query.product)
    color = _localized_color_term(query.color)
    parts = [query.brand, product, color]
    return " ".join(part for part in parts if part).strip() or build_search_text(task)


def _localized_product_term(product: str | None) -> str | None:
    if not product:
        return None
    return AVITO_PRODUCT_TERMS.get(product.lower(), product)


def _localized_color_term(color: str | None) -> str | None:
    if not color:
        return None
    return AVITO_COLOR_TERMS.get(color.lower(), color)


def _matches_query(product: RawProduct, task: ScrapeTaskAssigned) -> bool:
    query = task.query
    searchable_text = clean_text(f"{product.title} {product.url}").lower()
    if query.brand and query.brand.lower() not in searchable_text:
        return False
    if query.product:
        terms = PRODUCT_RELEVANCE_TERMS.get(query.product.lower(), {query.product.lower()})
        if not any(term in searchable_text for term in terms):
            return False
    return True


def _city_path_segment(task: ScrapeTaskAssigned) -> str:
    city = clean_text(task.query.city).lower() if task.query.city else "maroc"
    city = re.sub(r"[\s_]+", "-", city)
    city = re.sub(r"[^\w\-]+", "", city, flags=re.UNICODE).strip("-")
    return quote(city or "maroc")
