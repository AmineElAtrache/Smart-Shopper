"""Shared helpers for website scrapers."""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import urljoin

from shared.events.schemas import ProductQuery, ScrapeTaskAssigned

MAD_PRICE_RE = re.compile(r"(?P<amount>\d[\d\s.,]*)\s*(?:MAD|DH|DHS|درهم)?", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


def build_search_text(task: ScrapeTaskAssigned) -> str:
    query = task.query
    parts = [query.brand, query.product, query.color]
    return " ".join(part for part in parts if part).strip() or "phone"


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = TAG_RE.sub(" ", value)
    value = unescape(value)
    return SPACE_RE.sub(" ", value).strip()


def parse_mad_price(value: str | None) -> float | None:
    text = clean_text(value)
    match = MAD_PRICE_RE.search(text)
    if not match:
        return None
    amount = match.group("amount")
    amount = amount.replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return float(amount)
    except ValueError:
        return None


def absolute_url(base_url: str, href: str | None) -> str | None:
    if not href:
        return None
    return urljoin(base_url, href)


def budget_allows(price: float, query: ProductQuery) -> bool:
    if query.budget is None:
        return True
    return price <= query.budget * 1.25
