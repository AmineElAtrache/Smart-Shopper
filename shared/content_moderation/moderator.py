"""Outbound content moderation for user-facing Smart Shopper messages."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from shared.content_moderation.terms import (
    PROFANITY_PATTERNS,
    TOXIC_PATTERNS,
    UNAUTHORIZED_PATTERNS,
)

LEETSPEAK_TABLE = str.maketrans(
    {
        "@": "a",
        "0": "o",
        "1": "i",
        "3": "e",
        "$": "s",
        "4": "a",
        "5": "s",
        "7": "t",
    }
)
REPEATED_CHAR_PATTERN = re.compile(r"(.)\1{2,}")
WHITESPACE_PATTERN = re.compile(r"\s+")


@dataclass(frozen=True)
class ModerationFinding:
    category: str
    reason: str
    match: str


@dataclass(frozen=True)
class ModerationResult:
    allowed: bool
    findings: tuple[ModerationFinding, ...]

    @property
    def summary(self) -> str:
        if not self.findings:
            return "allowed"
        return "; ".join(f"{finding.category}:{finding.reason}" for finding in self.findings)


def normalize_for_moderation(text: str) -> str:
    """Normalize text to improve profanity and phrase detection."""
    normalized = unicodedata.normalize("NFKC", text or "")
    normalized = normalized.translate(LEETSPEAK_TABLE)
    normalized = normalized.lower()
    normalized = REPEATED_CHAR_PATTERN.sub(r"\1\1", normalized)
    normalized = WHITESPACE_PATTERN.sub(" ", normalized).strip()
    return normalized


def _redact_match(value: str, *, max_length: int = 24) -> str:
    cleaned = WHITESPACE_PATTERN.sub(" ", value.strip())
    if len(cleaned) <= max_length:
        return cleaned
    return f"{cleaned[: max_length - 3]}..."


def _append_pattern_findings(
    findings: list[ModerationFinding],
    *,
    category: str,
    text: str,
    patterns: tuple[re.Pattern[str], ...] | tuple[tuple[str, re.Pattern[str]], ...],
) -> None:
    if patterns and isinstance(patterns[0], tuple):
        typed_patterns = patterns  # type: ignore[assignment]
        for reason, pattern in typed_patterns:
            match = pattern.search(text)
            if match is not None:
                findings.append(
                    ModerationFinding(
                        category=category,
                        reason=reason,
                        match=_redact_match(match.group(0)),
                    )
                )
        return

    for pattern in patterns:
        match = pattern.search(text)
        if match is not None:
            findings.append(
                ModerationFinding(
                    category=category,
                    reason="profanity",
                    match=_redact_match(match.group(0)),
                )
            )


def moderate_outbound_text(text: str, *, enabled: bool = True) -> ModerationResult:
    """Evaluate outbound user-facing text against content policy."""
    if not enabled:
        return ModerationResult(allowed=True, findings=())

    candidate = (text or "").strip()
    if not candidate:
        return ModerationResult(allowed=True, findings=())

    normalized = normalize_for_moderation(candidate)
    findings: list[ModerationFinding] = []

    _append_pattern_findings(
        findings,
        category="profanity",
        text=normalized,
        patterns=PROFANITY_PATTERNS,
    )
    _append_pattern_findings(
        findings,
        category="toxic",
        text=normalized,
        patterns=TOXIC_PATTERNS,
    )
    _append_pattern_findings(
        findings,
        category="unauthorized",
        text=candidate,
        patterns=UNAUTHORIZED_PATTERNS,
    )
    _append_pattern_findings(
        findings,
        category="unauthorized",
        text=normalized,
        patterns=UNAUTHORIZED_PATTERNS,
    )

    deduped: list[ModerationFinding] = []
    seen: set[tuple[str, str, str]] = set()
    for finding in findings:
        key = (finding.category, finding.reason, finding.match)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(finding)

    return ModerationResult(allowed=not deduped, findings=tuple(deduped))


def infer_blocked_message_language(text: str) -> str:
    """Pick a safe fallback language bucket from the original user text."""
    sample = (text or "").lower()
    if re.search(
        r"\b(bghit|bgha|3afak|smah|chno|wach|kayn|kan9leb|3la|b\s|3awd)\b",
        sample,
    ):
        return "darija"
    if re.search(r"[\u0600-\u06FF]", sample):
        return "ar"
    if re.search(r"\b(bonjour|salut|merci|cherche|telephone|budget)\b", sample):
        return "fr"
    return "en"


BLOCKED_OUTBOUND_MESSAGES: dict[str, str] = {
    "en": (
        "Sorry, I can't send that response. "
        "Please ask about a product, brand, budget, or store."
    ),
    "fr": (
        "Desole, je ne peux pas envoyer cette reponse. "
        "Posez une question sur un produit, une marque, un budget ou un magasin."
    ),
    "darija": (
        "Smah liya, ma nقدرش nseft had jawab. "
        "3awd sowl 3la produit, brand, budget wla site."
    ),
    "ar": (
        "عذرا، لا يمكنني إرسال هذا الرد. "
        "يرجى السؤال عن منتج أو ماركة أو ميزانية أو متجر."
    ),
}


def blocked_outbound_message(*, language_hint: str | None = None, reference_text: str = "") -> str:
    language = language_hint or infer_blocked_message_language(reference_text)
    return BLOCKED_OUTBOUND_MESSAGES.get(language, BLOCKED_OUTBOUND_MESSAGES["en"])


def apply_outbound_moderation(
    text: str,
    *,
    fallback: str,
    enabled: bool = True,
    reference_text: str = "",
) -> tuple[str, ModerationResult]:
    """Return safe outbound text and the moderation result."""
    result = moderate_outbound_text(text, enabled=enabled)
    if result.allowed:
        return text, result
    safe_fallback = fallback or blocked_outbound_message(reference_text=reference_text)
    return safe_fallback, result
