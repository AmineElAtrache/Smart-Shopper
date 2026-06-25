"""Sanitize LLM prose before it reaches users."""

from __future__ import annotations

import re

REPETITION_PATTERN = re.compile(r"(.{2,24}?)\1{4,}", re.IGNORECASE)
SENTENCE_END = re.compile(r"[.!?؟…]\s+")
BIASED_LANGUAGE_PATTERN = re.compile(
    r"\b("
    r"best|recommend|recommended|top pick|first choice|start with|buy this|"
    r"meilleur|meilleure|meilleures|commence|verifie|acheter|a7sen|ahsen|l-ahsen|l'ahsen|"
    r"l-ula hiya|option 1|option #1|strong value|trusted source|good option|"
    r"solid|bda b|qbel ma tchri|open the best|help you choose|mzyanin|mzyanat"
    r")\b",
    re.IGNORECASE,
)

NEUTRALITY_DISCLAIMER_PATTERN = re.compile(
    r"\b("
    r"without favoring|no recommendation|not recommending|unbiased|no bias|not biased|"
    r"objectively neutral|remain neutral|stay neutral|not pushing|no influence|"
    r"don't influence|do not influence|sans favoriser|sans parti pris|"
    r"pas de recommandation|neutre|pas d'influence|"
    r"bla tafdil|bla bias|bla ma n-favori|bla ma n-pushi|la tawsiya|la pression|"
    r"tartib neutral|m-neutre|m-pushi|without bias|no favoritism"
    r")\b|"
    r"دون تفضيل|محايد|بدون تحيز",
    re.IGNORECASE,
)

STOP_SUFFIX_PATTERN = re.compile(r"\s+STOP\.?$", re.IGNORECASE)


def sanitize_llm_prose(text: str, *, max_length: int = 320) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip().strip('"')
    cleaned = STOP_SUFFIX_PATTERN.sub("", cleaned).strip()
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


def is_neutral_prose(text: str) -> bool:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return False
    return BIASED_LANGUAGE_PATTERN.search(cleaned) is None


def mentions_neutrality_disclaimer(text: str) -> bool:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return False
    return NEUTRALITY_DISCLAIMER_PATTERN.search(cleaned) is not None


def is_objective_prose(text: str) -> bool:
    return is_neutral_prose(text) and not mentions_neutrality_disclaimer(text)
