"""Shared product-category matching to drop accessories and false positives."""

from __future__ import annotations

import re

CATEGORY_PRIMARY_TERMS: dict[str, set[str]] = {
    "phone": {
        "phone", "phones", "smartphone", "smartphones", "telephone", "telephones", "mobile",
        "mobiles", "iphone", "android", "gsm", "telefon", "telephone portable",
    },
    "laptop": {
        "laptop", "laptops", "notebook", "notebooks", "macbook", "ordinateur portable",
        "pc portable", "portable", "ultrabook", "chromebook",
    },
    "tablet": {"tablet", "tablets", "tablette", "tablettes", "ipad"},
    "tv": {"tv", "television", "televiseur", "smart tv"},
    "fridge": {"fridge", "refrigerator", "refrigerateur", "congelateur", "freezer"},
    "air fryer": {"air fryer", "airfryer", "friteuse", "friteuse sans huile", "fryer"},
    "apartment": {"apartment", "appartement", "appartements", "studio", "duplex", "flat"},
    "car": {"voiture", "automobile", "tomobile", "vehicule", "vehicle"},
}

CATEGORIES_REQUIRING_STRONG_MATCH: frozenset[str] = frozenset(
    {"phone", "laptop", "tablet", "tv", "fridge", "air fryer"}
)

ACCESSORY_NEGATIVE_TERMS: dict[str, set[str]] = {
    "phone": {
        "headphone", "headphones", "earphone", "earphones", "earbud", "earbuds", "ecouteur",
        "ecouteurs", "microphone", "micro", "charger", "chargeur", "case", "cover", "coque",
        "cable", "câble", "protector", "glass", "support", "stand", "whey", "protein",
        "nitrotech", "smarttag", "smart tag", "galaxy tag", "airtag", "air tag", "tracker",
        "trackr", "localisateur", "bracelet", "band", "strap", "watch band", "powerbank",
        "power bank", "batterie externe", "adaptateur", "adapter", "pochette", "etui",
        "étui", "screen protector", "protection ecran", "film", "tempered", "holder",
        "mount", "ring light", "selfie stick", "monopod", "stylus pen", "pen tablet",
        "buds", "airpods", "air pods", "watch", "montre", "smartwatch", "smart watch",
        "fitness band", "fitness tracker", "connecte", "connecté", "connected bracelet",
    },
    "laptop": {
        "stand", "support", "sleeve", "bag", "sac", "charger", "chargeur", "battery",
        "adapter", "adaptateur", "dock", "cooler", "cooling", "clavier", "keyboard",
        "mouse", "souris", "hub", "usb hub", "webcam", "monitor", "screen", "ecran",
        "ram ", "memory module", "ssd enclosure", "hdd enclosure",
    },
    "tablet": {
        "case", "cover", "coque", "keyboard", "clavier", "stylus", "pen", "screen protector",
        "holder", "stand", "support", "table basse", "table a manger", "table de salon",
        "table de chevet", "chaise", "canape", "sofa", "meuble", "furniture",
    },
    "tv": {
        "support", "stand", "mount", "bracket", "remote", "telecommande", "cable", "hdmi",
        "antenna", "antenne", "decoder", "decodage", "box only",
    },
    "fridge": {
        "handle", "poignee", "shelf", "etagere", "filter", "filtre", "water dispenser",
    },
    "air fryer": {
        "macbook", "macbook air", "laptop", "ordinateur", "pc", "climatiseur", "clim",
        "air cooler", "air coolers", "cooler", "conditioner", "ventilateur", "airpods",
        "air pods", "air max", "nike air", "refroidisseur", "grill pan", "basket only",
    },
    "table": {
        "tablet", "tablette", "tablettes", "ipad", "tabla", "wacom", "pen tablet",
        "تابلت", "طابلات",
    },
    "apartment": {"villa", "maison", "terrain", "local commercial", "bureau", "entrepot"},
}

PHONE_MODEL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"galaxy\s+[amsfz]\d", re.IGNORECASE),
    re.compile(r"galaxy\s+note", re.IGNORECASE),
    re.compile(r"galaxy\s+ultra", re.IGNORECASE),
    re.compile(r"galaxy\s+jump", re.IGNORECASE),
    re.compile(r"redmi\s+\w+", re.IGNORECASE),
    re.compile(r"poco\s+\w+", re.IGNORECASE),
    re.compile(r"iphone\s+\d", re.IGNORECASE),
    re.compile(r"iphone\s+[se|xr|xs|pro|plus|mini]", re.IGNORECASE),
    re.compile(r"itel\s+[a-z]?\d", re.IGNORECASE),
    re.compile(r"tecno\s+\w+", re.IGNORECASE),
    re.compile(r"infinix\s+\w+", re.IGNORECASE),
    re.compile(r"honor\s+\w+", re.IGNORECASE),
    re.compile(r"oppo\s+[a-z]?\d", re.IGNORECASE),
    re.compile(r"realme\s+\w+", re.IGNORECASE),
    re.compile(r"vivo\s+\w+", re.IGNORECASE),
    re.compile(r"pixel\s+\d", re.IGNORECASE),
    re.compile(r"nova\s+\d", re.IGNORECASE),
)

LAPTOP_MODEL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"macbook\s+(air|pro)", re.IGNORECASE),
    re.compile(r"thinkpad", re.IGNORECASE),
    re.compile(r"ideapad", re.IGNORECASE),
    re.compile(r"elitebook", re.IGNORECASE),
    re.compile(r"probook", re.IGNORECASE),
    re.compile(r"victus", re.IGNORECASE),
    re.compile(r"\bomen\b", re.IGNORECASE),
    re.compile(r"vivobook", re.IGNORECASE),
    re.compile(r"zenbook", re.IGNORECASE),
    re.compile(r"latitude", re.IGNORECASE),
    re.compile(r"inspiron", re.IGNORECASE),
    re.compile(r"legion", re.IGNORECASE),
    re.compile(r"predator", re.IGNORECASE),
    re.compile(r"core\s+i[3579]", re.IGNORECASE),
    re.compile(r"ryzen\s+[3579]", re.IGNORECASE),
)

MODEL_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "phone": PHONE_MODEL_PATTERNS,
    "laptop": LAPTOP_MODEL_PATTERNS,
}


def normalize_product_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[_\W]+", " ", value.lower())).strip()


def contains_any_term(text: str, terms: set[str]) -> bool:
    return any(has_term(text, term) for term in terms)


def contains_any_negative(text: str, terms: set[str]) -> bool:
    compact = re.sub(r"\s+", "", text)
    for term in terms:
        normalized_term = normalize_product_text(term)
        token = re.sub(r"\s+", "", normalized_term)
        if len(token) <= 2:
            continue
        if token in compact:
            return True
        if " " in normalized_term and normalized_term in text:
            return True
        if has_term(text, normalized_term):
            return True
    return False


def has_term(text: str, term: str) -> bool:
    normalized_term = normalize_product_text(term)
    if len(normalized_term) <= 1:
        return False
    if " " in normalized_term:
        return normalized_term in text
    return re.search(rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])", text) is not None


def matches_model_pattern(text: str, category: str) -> bool:
    patterns = MODEL_PATTERNS.get(category, ())
    return any(pattern.search(text) for pattern in patterns)


def matches_category_product(
    text: str,
    category: str,
    *,
    brand: str | None = None,
    loose_aliases: set[str] | None = None,
) -> bool:
    normalized = normalize_product_text(text)
    negatives = ACCESSORY_NEGATIVE_TERMS.get(category, set())
    if contains_any_negative(normalized, negatives):
        return False

    primary = CATEGORY_PRIMARY_TERMS.get(category, set())
    if primary and contains_any_term(normalized, primary):
        return True

    if matches_model_pattern(normalized, category):
        return True

    if category == "phone" and loose_aliases and contains_any_term(normalized, loose_aliases):
        return True

    if category not in CATEGORIES_REQUIRING_STRONG_MATCH:
        aliases = loose_aliases or {category}
        return contains_any_term(normalized, aliases)

    if brand and normalize_product_text(brand) in normalized:
        return False

    if loose_aliases and contains_any_term(normalized, loose_aliases):
        return False

    return False


def is_implausible_accessory_price(
    *,
    title: str,
    url: str,
    price: float,
    category: str,
    budget: float | None,
    brand: str | None = None,
    loose_aliases: set[str] | None = None,
) -> bool:
    if budget is None or budget < 500:
        return False
    if price >= budget * 0.35:
        return False
    if category not in CATEGORIES_REQUIRING_STRONG_MATCH:
        return False
    searchable = normalize_product_text(f"{title} {url}")
    return not matches_category_product(
        searchable,
        category,
        brand=brand,
        loose_aliases=loose_aliases,
    )
