"""Behavior inference helpers for private generator memory."""

from __future__ import annotations

import re
import unicodedata

from shared.events.schemas import DecisionRanked

_ARABIC_SCRIPT = re.compile(r"[\u0600-\u06FF]")

LANGUAGE_GUIDANCE = {
    "darija": "Moroccan Darija / Arabizi (same style as the user message)",
    "fr": "French",
    "ar": "Modern Standard Arabic",
    "en": "English",
}

_DARIJA_TOKENS = re.compile(
    r"\b("
    r"slm|salam|labas|lbess|lbs|kidayer|kidayr|kifach|bghit|bghiti|kan9leb|kan9le|"
    r"chno|chnahoma|chnahuma|wach|3afak|3lik|3likom|b7al|sbah|ahlan|n9leb|9leb|"
    r"chi|kayn|afak|dyal|tilifun|mizaniya|taman|mdina|bghiti|kif dayr|"
    r"kaydur|kaydir|kader|kadero|katdir|lboot|boot|hadi|had|goul|goli|"
    r"kan3awen|n3awen|n9leb|lbas|cv"
    r")\b",
    re.IGNORECASE,
)
_FR_TOKENS = re.compile(
    r"\b("
    r"bonjour|salut|bonsoir|coucou|merci|svp|comment|commen|cherch|cherche|recherche|"
    r"prix|budget|quoi|service|services|vous|chercher|une|des|du|acheter|telephone|"
    r"portable|ordinateur|moins|maximum|bonne|journee|ca va|cava|est ce|quels|quel"
    r")\b",
    re.IGNORECASE,
)
_EN_TOKENS = re.compile(
    r"\b("
    r"hi|hello|hey|how|are|you|what|service|services|offer|offers|do|does|help|"
    r"looking|thanks|please|want|need|your|the|and|for|can|who|phone|buy|budget|"
    r"under|price|search|find|compare"
    r")\b",
    re.IGNORECASE,
)
_FR_PHRASES = re.compile(
    r"(?:comment|commen)\s*(?:ca|cava|sa)\s*va?|\b(?:ca|cava|ça)\s+va\b",
    re.IGNORECASE,
)
_EN_PHRASES = re.compile(
    r"\bhow are you\b|\bwhat (?:do|can|it) you\b|\bwhat you do\b|"
    r"\bwhat service\b|\bwhat services\b|\bwho are you\b",
    re.IGNORECASE,
)
_DARIJA_PHRASES = re.compile(
    r"\blabas 3lik\b|\bkidayer\b|\bkidayr\b|\bkifach dayr\b|\blbs 3lik\b|"
    r"\bchno katdir\b|\bash katdir\b|\bslm kidayer\b|"
    r"\bchnahoma\b|\bchnahuma\b|\bkaydur had\b|\bchno kaydur\b|\bli kader\b|"
    r"\bles services li\b|\bhad lboot\b|\bhad l-boot\b",
    re.IGNORECASE,
)
_STRONG_DARIJA = re.compile(
    r"\b("
    r"chno|chnahoma|chnahuma|bghit|bghiti|kan9leb|3lik|3likom|3afak|"
    r"kaydur|kaydir|kader|kadero|katdir|lboot|slm|kidayer|kidayr|labas|"
    r"n9leb|9leb|wach|mizaniya|chnah|lbas"
    r")\b",
    re.IGNORECASE,
)


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def infer_language(text: str) -> str:
    if _ARABIC_SCRIPT.search(text):
        return "ar"

    normalized = _strip_accents((text or "").lower())

    if _STRONG_DARIJA.search(normalized):
        return "darija"
    if _DARIJA_PHRASES.search(normalized):
        return "darija"
    if _FR_PHRASES.search(normalized):
        return "fr"
    if _EN_PHRASES.search(normalized):
        return "en"

    darija_hits = len(_DARIJA_TOKENS.findall(normalized))
    fr_hits = len(_FR_TOKENS.findall(normalized))
    en_hits = len(_EN_TOKENS.findall(normalized))

    if darija_hits and (darija_hits >= fr_hits or darija_hits >= en_hits):
        return "darija"
    if fr_hits > en_hits:
        return "fr"
    if en_hits > fr_hits:
        return "en"
    if any(char in text for char in "éèêëàâùûçîïô"):
        return "fr"
    if darija_hits:
        return "darija"
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
