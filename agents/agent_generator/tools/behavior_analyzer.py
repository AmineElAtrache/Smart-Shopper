"""Behavior inference helpers for private generator memory."""

from __future__ import annotations


def infer_language(text: str) -> str:
    normalized = text.lower()
    if any(token in normalized for token in ("bghit", "kan9leb", "chi", "wach", "kayn")):
        return "darija"
    if any(token in normalized for token in ("bonjour", "prix", "cherche", "moins cher")):
        return "fr"
    return "en"


def infer_tone(text: str) -> str:
    normalized = text.lower()
    if any(token in normalized for token in ("please", "merci", "afak", "svp")):
        return "friendly"
    if len(text) < 40:
        return "concise"
    return "detailed"
