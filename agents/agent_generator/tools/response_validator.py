"""Validation helpers for generated shopping responses."""

from __future__ import annotations

import re

from shared.events.schemas import DecisionRanked, RankedProduct

URL_PATTERN = re.compile(r"https?://[^\s)]+")


class ResponseValidationError(ValueError):
    """Raised when an LLM response drops or changes critical product facts."""


def validate_response(event: DecisionRanked, message: str) -> None:
    if not message.strip():
        raise ResponseValidationError("empty_response")
    if not event.products:
        return

    allowed_urls = {str(product.url).rstrip("/") for product in event.products[:3]}
    mentioned_urls = {url.rstrip("/.,") for url in URL_PATTERN.findall(message)}
    unknown_urls = mentioned_urls - allowed_urls
    if unknown_urls:
        raise ResponseValidationError(f"unknown_urls:{sorted(unknown_urls)}")

    for product in event.products[:3]:
        _validate_product_facts(product, message)


def _validate_product_facts(product: RankedProduct, message: str) -> None:
    normalized = message.lower()
    title_tokens = [token for token in re.split(r"\W+", product.title.lower()) if len(token) >= 3]
    if title_tokens and not any(token in normalized for token in title_tokens[:4]):
        raise ResponseValidationError(f"missing_title:{product.title}")

    price_text = f"{product.price:g}"
    if price_text not in message:
        raise ResponseValidationError(f"missing_price:{price_text}")

    if product.source.lower() not in normalized:
        raise ResponseValidationError(f"missing_source:{product.source}")

    if str(product.url).rstrip("/") not in message.replace("/\n", "/"):
        raise ResponseValidationError(f"missing_url:{product.url}")
