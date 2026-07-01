"""Palmarosa Shop (palmarosashop.com) scraper provider."""

from __future__ import annotations

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
from agents.webscraping.tools.playwright_scraper import fetch_rendered_html
from shared.events.schemas import Availability, RawProduct, ScrapeTaskAssigned

PALMAROSA_BASE_URL = "https://www.palmarosashop.com"
PALMAROSA_SEARCH_URL = "https://www.palmarosashop.com/search?q={query}"
PRODUCT_TERMS = {
    "perfume": "parfum",
    "makeup": "maquillage",
    "skincare": "soin visage",
    "shampoo": "shampooing",
    "cream": "creme",
}
PRODUCT_MATCH_TERMS = {
    "perfume": {"perfume", "parfum", "eau de parfum", "eau de toilette", "fragrance"},
    "makeup": {"makeup", "maquillage", "mascara", "lipstick", "rouge"},
    "skincare": {"skincare", "soin", "serum", "creme", "crème"},
    "shampoo": {"shampoo", "shampooing", "cheveux"},
}
PRICE_RE = re.compile(
    r"(?P<amount>\d{1,4}(?:[,\.]\d{2})?)\s*(?:MAD|DH|DHS|dh|dhs|mad)",
    re.IGNORECASE,
)
SKIP_SLUGS = {
    "search",
    "compte",
    "panier",
    "marques",
    "promotions",
    "parfum",
    "maquillage",
    "cheveux",
    "soin-visage",
    "corps-bain",
    "type-de-peau",
}


def build_search_url(task: ScrapeTaskAssigned) -> str:
    return PALMAROSA_SEARCH_URL.format(query=quote_plus(_build_palmarosa_search_text(task)))


async def scrape(task: ScrapeTaskAssigned, *, timeout: float = 15.0) -> list[RawProduct]:
    url = build_search_url(task)
    html, page_url = await fetch_rendered_html(
        url,
        timeout=timeout,
        locale="fr-MA",
        wait_for_selector='a[href*="-"]',
    )
    return parse_products(html, task, page_url=page_url)


def parse_products(html: str, task: ScrapeTaskAssigned, *, page_url: str | None = None) -> list[RawProduct]:
    page_url = page_url or build_search_url(task)
    return _dedupe_and_filter(_parse_dom_products(html, task, page_url=page_url), task)


def _parse_dom_products(html: str, task: ScrapeTaskAssigned, *, page_url: str) -> list[RawProduct]:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    soup = BeautifulSoup(html, "html.parser")
    products: list[RawProduct] = []
    seen_urls: set[str] = set()
    for card in soup.select("div.border.rounded-xl, article, li.product"):
        block_text = clean_text(card.get_text(" ", strip=True))
        price = _extract_sale_price(block_text)
        if price is None:
            continue
        anchor = card.select_one('a[href*="-"]')
        if anchor is None:
            continue
        url = _clean_product_url(absolute_url(page_url, anchor.get("href")))
        if not url or url in seen_urls:
            continue
        title = _extract_title(card, anchor, block_text)
        if not title:
            continue
        seen_urls.add(url)
        products.append(
            _raw_product(
                task,
                title=title,
                price=price,
                url=url,
                metadata={"parser": "dom_card", "category": "beauty"},
            )
        )
    return products


def _extract_title(card, anchor, block_text: str) -> str:
    image = card.select_one("img[alt]")
    if image is not None:
        title = clean_text(image.get("alt"))
        if title and _extract_sale_price(title) is None:
            return title
    title_node = card.select_one(".truncate, .font-bold.text-ink")
    if title_node is not None:
        title = clean_text(title_node.get_text(" ", strip=True))
        if title and _extract_sale_price(title) is None:
            return title
    for attr in ("aria-label", "title"):
        title = clean_text(anchor.get(attr))
        if title and _extract_sale_price(title) is None:
            return title
    return _title_before_price(block_text)


def _title_before_price(text: str) -> str:
    return clean_text(re.split(r"MAD|DH|DHS|-\d+%", text, maxsplit=1, flags=re.IGNORECASE)[0])


def _extract_sale_price(text: str) -> float | None:
    prices = [_parse_price(match.group(0)) for match in PRICE_RE.finditer(text)]
    prices = [price for price in prices if price is not None]
    return prices[0] if prices else None


def _parse_price(value: str | None) -> float | None:
    if not value:
        return None
    match = PRICE_RE.search(clean_text(value))
    if not match:
        return None
    raw_amount = match.group("amount").replace(",", ".")
    try:
        return float(raw_amount)
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
        source="palmarosa",
        title=title,
        price=price,
        currency=task.query.currency,
        url=url,
        availability=availability,
        seller="Palmarosa Shop",
        rating=None,
        metadata=metadata,
    )


def _clean_product_url(url: str | None) -> str | None:
    if not url or "palmarosashop.com" not in url:
        return None
    cleaned = url.split("?", 1)[0].split("#", 1)[0]
    slug = cleaned.rsplit("/", 1)[-1]
    if slug in SKIP_SLUGS:
        return None
    if slug.count("-") < 2:
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


def _build_palmarosa_search_text(task: ScrapeTaskAssigned) -> str:
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
