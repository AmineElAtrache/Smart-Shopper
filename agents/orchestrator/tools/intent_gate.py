"""Decide whether an inbound message should trigger product search."""

from __future__ import annotations

import re

from shared.events.schemas import ProductQuery

GREETING_ONLY_PATTERN = re.compile(
    r"^(?:"
    r"slm|salam|salamu|labas|lbess|lbs|sbah|sbah lkhir|bsah|ahlan|"
    r"hi|hello|hey|yo|"
    r"bonjour|salut|coucou|bjr|bsr|cc|"
    r"مرحبا|سلام|السلام عليكم|"
    r"kifach|kidayr|kidayer|labas 3lik|labas 3likom|lbs 3lik"
    r")[\s!?.,\u061f]*$",
    re.IGNORECASE,
)

CONVERSATIONAL_PATTERN = re.compile(
    r"(?:"
    r"\bhow are you\b|\bwhat do you\b|\bwhat you do\b|\bwhat service\b|\bwhat services\b|"
    r"\bwhat it service\b|\bwho are you\b|\bwhat can you\b|"
    r"(?:comment|commen)\s*(?:ca|cava|sa)\s*va?|"
    r"\b(?:ca|cava|ça)\s+va\b|"
    r"\bkifach\b|\bkidayer\b|\bkidayr\b|\blabas 3lik\b|\blbs 3lik\b|"
    r"\bchno katdir\b|\bash katdir\b|"
    r"\bchnahoma\b|\bchnahuma\b|\bkaydur\b|\bkaydir\b|\bkadero\b|\bkader\b|"
    r"\bhad lboot\b|\bhad l-boot\b|\bles services li\b|"
    r"\bqu(?:'| )?est[- ]ce que\b|\bquels services\b|\bcomment ca va\b"
    r")",
    re.IGNORECASE,
)

EXPLICIT_SHOPPING_INTENT = re.compile(
    r"\b("
    r"bghit|bghiti|kan9leb|kan9le|n9leb|9leb|"
    r"cherche|cherch|recherche|looking for|lookin for|want to buy|need to buy|"
    r"want|need|buy|acheter|commander|under|moins de|max|maximum"
    r")\b",
    re.IGNORECASE,
)

SHOPPING_SIGNAL_PATTERN = re.compile(
    r"\b("
    r"bghit|bghiti|kan9leb|kan9le|n9leb|9leb|3la|wach|chno|"
    r"cherche|cherch|recherche|looking|lookin|want|need|buy|"
    r"phone|tilifun|telephone|smartphone|mobile|laptop|pc|portable|"
    r"fridge|telaja|voiture|tomobile|chaussure|snniitra|"
    r"samsung|iphone|apple|hp|xiaomi|huawei|"
    r"prix|taman|budget|mizaniya|dh|mad|dhs|dirham|"
    r"under|moins|max|maximum"
    r")\b",
    re.IGNORECASE,
)

PRODUCT_HINT_PATTERN = re.compile(
    r"\b("
    r"phone|tilifun|telephone|laptop|pc|portable|fridge|telaja|voiture|"
    r"chaussure|montre|watch|table|chair|kursi|camera|tv|tele|"
    r"samsung|iphone|apple|hp|xiaomi|huawei"
    r")\b",
    re.IGNORECASE,
)

GREETING_TOKEN_PATTERN = re.compile(
    r"\b(slm|salam|labas|lbs|lbess|hi|hello|hey|bonjour|salut|coucou)\b",
    re.IGNORECASE,
)


def normalize_message(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def is_greeting_only(text: str) -> bool:
    normalized = normalize_message(text)
    if not normalized:
        return True
    if GREETING_ONLY_PATTERN.match(normalized):
        return True
    if len(normalized.split()) <= 2 and not SHOPPING_SIGNAL_PATTERN.search(normalized):
        lowered = normalized.lower()
        if any(token in lowered for token in ("slm", "salam", "labas", "hello", "hi", "bonjour", "salut", "cava")):
            return True
    return False


def is_conversational_intent(text: str) -> bool:
    normalized = normalize_message(text)
    if not normalized:
        return True
    if CONVERSATIONAL_PATTERN.search(normalized):
        return True
    if is_greeting_only(normalized):
        return True
    words = normalized.split()
    if len(words) <= 6 and not EXPLICIT_SHOPPING_INTENT.search(normalized):
        if GREETING_TOKEN_PATTERN.search(normalized) and not PRODUCT_HINT_PATTERN.search(normalized):
            return True
    return False


def has_actionable_shopping_query(query: ProductQuery) -> bool:
    return bool(query.product or query.brand or query.budget is not None)


def should_run_product_search(text: str, query: ProductQuery) -> bool:
    normalized = normalize_message(text)
    if is_conversational_intent(normalized):
        return False

    word_count = len(normalized.split())
    has_explicit_intent = bool(
        EXPLICIT_SHOPPING_INTENT.search(normalized) or PRODUCT_HINT_PATTERN.search(normalized)
    )

    if has_actionable_shopping_query(query):
        if word_count <= 5 and not has_explicit_intent:
            return False
        return True

    return bool(SHOPPING_SIGNAL_PATTERN.search(normalized) and PRODUCT_HINT_PATTERN.search(normalized))
