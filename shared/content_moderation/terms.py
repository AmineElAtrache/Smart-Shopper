"""Content policy patterns for outbound message moderation."""

from __future__ import annotations

import re

# Word-boundary profanity across EN / FR / Darija (latin) / common AR transliterations.
PROFANITY_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE | re.UNICODE)
    for pattern in (
        r"\b(f+u+c+k+\w*|fuk+\w*|fck\w*|sh+i+t+|bitch|bastard|asshole|dick|pussy|cunt|whore|slut)\b",
        r"\b(merde|putain|salope|connard|encul[eé]|fdp|ntm|nique|baise)\b",
        r"\b(z+o+k+|zamel|9ahba|9ahbeh|l7wa|l7wa+|nik+|\bnikom+\b|\bnik+ek+\b|khr+|khra+)\b",
        r"\b(kus+em+|ks+em+|zbi+|zebi+)\b",
        r"(كسم|زبي|شرمو|قحب|نيك)",
    )
)

# Violence, hate, explicit sexual content, and self-harm cues.
TOXIC_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "violence",
        re.compile(
            r"\b("
            r"kill\s+(you|him|her|them)|"
            r"rape|murder|terrorist|bomb\s+threat|"
            r"shoot\s+you|cut\s+your|"
            r"qatl|qtal|dir\s+hom|"
            r"tuer|assassiner"
            r")\b",
            re.IGNORECASE | re.UNICODE,
        ),
    ),
    (
        "hate",
        re.compile(
            r"\b("
            r"nazi|white\s+power|heil\s+hitler|"
            r"death\s+to\s+(all\s+)?(jews|muslims|christians|blacks|whites)|"
            r"gas\s+the\s+jews"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "sexual_explicit",
        re.compile(
            r"\b("
            r"porn|porno|xxx|hentai|nude\s+pics|send\s+nudes|"
            r"sex\s+video|onlyfans\s+link"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "self_harm",
        re.compile(
            r"\b("
            r"kill\s+yourself|kys|suicide\s+method|self\s*[- ]?harm|"
            r"commit\s+suicide"
            r")\b",
            re.IGNORECASE,
        ),
    ),
)

# Jailbreaks, scams, credential harvesting, and obvious non-shopping spam.
UNAUTHORIZED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "prompt_injection",
        re.compile(
            r"(ignore\s+(all\s+)?(previous|prior)\s+instructions|"
            r"system\s+prompt|developer\s+message|"
            r"jailbreak|dan\s+mode|do\s+anything\s+now|"
            r"revele?\s+(le\s+)?(prompt|systeme|secret))",
            re.IGNORECASE,
        ),
    ),
    (
        "credential_harvest",
        re.compile(
            r"\b("
            r"password|mot\s+de\s+passe|"
            r"credit\s+card|cvv|iban|"
            r"otp\s+code|verification\s+code|"
            r"send\s+me\s+your\s+(login|token|api\s+key)"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "scam",
        re.compile(
            r"\b("
            r"wire\s+transfer|western\s+union|"
            r"you\s+won|claim\s+your\s+prize|free\s+iphone|"
            r"double\s+your\s+crypto|guaranteed\s+profit|"
            r"click\s+here\s+to\s+win|whatsapp\s+\+?\d{8,}"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "malware_markup",
        re.compile(
            r"(<script\b|javascript:|onerror\s*=|onload\s*=|<iframe\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "off_topic_spam",
        re.compile(
            r"\b("
            r"viagra|cialis|casino\s+bonus|bet\s+now|"
            r"forex\s+signals|pyramid\s+scheme|"
            r"mlm\s+opportunity|get\s+rich\s+quick"
            r")\b",
            re.IGNORECASE,
        ),
    ),
)
