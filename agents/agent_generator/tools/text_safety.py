"""Sanitize LLM prose before it reaches users."""

from __future__ import annotations

import re

REPETITION_PATTERN = re.compile(r"(.{2,24}?)\1{4,}", re.IGNORECASE)
SENTENCE_END = re.compile(r"[.!?؟…]\s+")


def sanitize_llm_prose(text: str, *, max_length: int = 320) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip().strip('"')
    if not cleaned:
        return ""

    match = REPETITION_PATTERN.search(cleaned)
    if match:
        cleaned = cleaned[: match.start()].strip()

    if len(cleaned) > max_length:
        trimmed = cleaned[:max_length]
        sentence_breaks = list(SENTENCE_END.finditer(trimmed))
        if sentence_breaks:
            cleaned = trimmed[: sentence_breaks[-1].start() + 1].strip()
        else:
            cleaned = trimmed.rsplit(" ", 1)[0].strip()

    return cleaned


def is_usable_prose(text: str, *, max_length: int = 320) -> bool:
    cleaned = sanitize_llm_prose(text, max_length=max_length)
    if len(cleaned) < 8:
        return False
    if REPETITION_PATTERN.search(cleaned):
        return False

    words = [word for word in re.split(r"\W+", cleaned.lower()) if word]
    if len(words) >= 6:
        counts: dict[str, int] = {}
        for word in words:
            counts[word] = counts.get(word, 0) + 1
        if max(counts.values()) / len(words) > 0.34:
            return False
    return True
