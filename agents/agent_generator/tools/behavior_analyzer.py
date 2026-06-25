"""Behavior inference helpers for private generator memory."""

from __future__ import annotations

import re

from shared.events.schemas import DecisionRanked

_ARABIC_SCRIPT = re.compile(r"[\u0600-\u06FF]")

LANGUAGE_GUIDANCE = {
    "darija": "Moroccan Darija / Arabizi (same style as the user message)",
    "fr": "French",
    "ar": "Modern Standard Arabic",
    "en": "English",
}


def infer_language(text: str) -> str:
    normalized = text.lower()
    if _ARABIC_SCRIPT.search(text):
        return "ar"
    if any(token in normalized for token in ("bghit", "kan9leb", "chi", "wach", "kayn", "3afak", "chno", "b7al", "salam", "labas")):
        return "darija"
    if any(
        token in normalized
        for token in ("bonjour", "prix", "cherche", "moins cher", "salut", "merci", "svp", "telephone")
    ):
        return "fr"
    return "en"


def infer_tone(text: str) -> str:
    normalized = text.lower()
    if any(token in normalized for token in ("please", "merci", "afak", "svp", "3afak")):
        return "friendly"
    if len(text) < 40:
        return "concise"
    return "detailed"


def resolve_generation_context(
    event: DecisionRanked,
    behavior_context: dict | None = None,
) -> dict:
    context = dict(behavior_context or {})
    if event.user_text:
        context["user_text"] = event.user_text
        context["language"] = infer_language(event.user_text)
        context["tone"] = infer_tone(event.user_text)
    else:
        context.setdefault("language", "en")
        context.setdefault("tone", "concise")
    context["language_guidance"] = LANGUAGE_GUIDANCE.get(str(context.get("language", "en")), "English")
    return context
