"""Helpers for detecting mock scrape/cache payloads."""

from __future__ import annotations

MOCK_URL_MARKERS = ("example.com", "https://example.com/")


def is_mock_response_text(text: str | None) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(marker in lowered for marker in MOCK_URL_MARKERS)


def is_mock_product_url(url: str | None) -> bool:
    if not url:
        return False
    return is_mock_response_text(str(url))
