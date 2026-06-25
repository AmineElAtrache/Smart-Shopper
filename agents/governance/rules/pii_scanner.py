"""PII scanner and masker for governance audits."""

from __future__ import annotations

import re

EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?212|0)\s?[5-7](?:[\s.-]?\d){8}(?!\d)")
TOKEN_PATTERN = re.compile(r"\b(?:token|api[_-]?key|secret)\s*[:=]\s*['\"]?([A-Za-z0-9._-]{16,})", re.IGNORECASE)


def find_pii(text: str) -> list[str]:
    findings: list[str] = []
    if EMAIL_PATTERN.search(text):
        findings.append("email")
    if PHONE_PATTERN.search(text):
        findings.append("phone")
    if TOKEN_PATTERN.search(text):
        findings.append("secret")
    return findings


def mask_pii(text: str) -> str:
    masked = EMAIL_PATTERN.sub("[email]", text)
    masked = PHONE_PATTERN.sub("[phone]", masked)
    return TOKEN_PATTERN.sub(lambda match: match.group(0).replace(match.group(1), "[secret]"), masked)
