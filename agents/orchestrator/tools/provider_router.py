"""Pick marketplace providers that match the requested product category."""

from __future__ import annotations

import re

from agents.orchestrator.tools.provider_capabilities import prioritize_sites_for_query

SPACE_RE = re.compile(r"\s+")
UNDERSCORE_RE = re.compile(r"_+")

DEFAULT_SITES = [
    "jumia",
    "avito",
    "electrosalam",
    "mafiawaystore",
    "moteur",
    "mymarket",
    "ultrapc",
    "electroplanet",
    "defacto",
    "biougnach",
    "marjane",
    "decathlon",
    "mubawab",
    "ikea",
    "palmarosa",
    "bringo",
    "planetsport",
]
UNDERSCORE_RE = re.compile(r"_+")


def normalize_product_key(product: str | None) -> str:
    if not product:
        return ""
    key = product.strip().lower()
    key = UNDERSCORE_RE.sub("_", key)
    key = SPACE_RE.sub(" ", key)
    return key


# ~6–8 relevant sites per category (fits ~80s scrape budget with concurrency 6).
CATEGORY_SITES: dict[str, tuple[str, ...]] = {
    "phone": (
        "jumia",
        "avito",
        "electrosalam",
        "ultrapc",
        "electroplanet",
        "biougnach",
    ),
    "laptop": (
        "electrosalam",
        "ultrapc",
        "jumia",
        "avito",
        "electroplanet",
    ),
    "appliance": (
        "electroplanet",
        "biougnach",
        "jumia",
        "avito",
        "electrosalam",
    ),
    "car": ("moteur", "avito"),
    "real_estate": ("mubawab", "avito"),
    "fashion": ("defacto", "mafiawaystore", "jumia"),
    "sports": ("decathlon", "planetsport", "jumia"),
    "grocery": ("marjane", "mymarket", "bringo"),
    "beauty": ("palmarosa", "jumia"),
    "furniture": ("ikea", "avito", "jumia"),
    "general": ("jumia", "avito", "electroplanet", "electrosalam"),
}

PRODUCT_TO_CATEGORY: dict[str, str] = {
    # Phones
    "phone": "phone",
    "smartphone": "phone",
    "iphone": "phone",
    "pro max": "phone",
    "pro": "phone",
    "galaxy": "phone",
    "redmi": "phone",
    "mobile": "phone",
    "telephone": "phone",
    # Laptops / PC
    "laptop": "laptop",
    "pc": "laptop",
    "desktop": "laptop",
    "omen": "laptop",
    "gaming pc": "laptop",
    "gaming_pc": "laptop",
    "monitor": "laptop",
    "keyboard": "laptop",
    "mouse": "laptop",
    "headphones": "laptop",
    "casque": "laptop",
    "tablet": "laptop",
    # Home appliances & TV
    "tv": "appliance",
    "television": "appliance",
    "fridge": "appliance",
    "refrigerator": "appliance",
    "freezer": "appliance",
    "washing machine": "appliance",
    "washing_machine": "appliance",
    "air conditioner": "appliance",
    "air_conditioner": "appliance",
    "air fryer": "appliance",
    "airfryer": "appliance",
    "friteuse sans huile": "appliance",
    "ac": "appliance",
    "climatiseur": "appliance",
    "microwave": "appliance",
    "oven": "appliance",
    # Vehicles
    "car": "car",
    "voiture": "car",
    "auto": "car",
    "golf": "car",
    "renault": "car",
    "dacia": "car",
    # Real estate
    "apartment": "real_estate",
    "appartement": "real_estate",
    "villa": "real_estate",
    "house": "real_estate",
    "maison": "real_estate",
    "rent": "real_estate",
    # Fashion
    "shirt": "fashion",
    "t-shirt": "fashion",
    "tshirt": "fashion",
    "jacket": "fashion",
    "dress": "fashion",
    "pants": "fashion",
    # Sports
    "shoes": "sports",
    "chaussure": "sports",
    "sneakers": "sports",
    "running shoes": "sports",
    # Grocery
    "milk": "grocery",
    "lait": "grocery",
    "eggs": "grocery",
    "oil": "grocery",
    "zit": "grocery",
    "bread": "grocery",
    # Beauty
    "perfume": "beauty",
    "parfum": "beauty",
    "makeup": "beauty",
    "cosmetic": "beauty",
    # Furniture
    "chair": "furniture",
    "desk": "furniture",
    "table": "furniture",
    "sofa": "furniture",
    "bed": "furniture",
}

ROUTING_CATEGORIES = tuple(CATEGORY_SITES.keys())


def _category_alias_matches(alias: str, key: str) -> bool:
    if alias == key:
        return True
    if " " in alias or " " in key:
        return alias in key or key in alias
    alias_pattern = rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"
    key_pattern = rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])"
    return re.search(alias_pattern, key) is not None or re.search(key_pattern, alias) is not None


def classify_product(product: str | None) -> str:
    key = normalize_product_key(product)
    if not key:
        return "general"
    if key in PRODUCT_TO_CATEGORY:
        return PRODUCT_TO_CATEGORY[key]
    for alias, category in sorted(PRODUCT_TO_CATEGORY.items(), key=lambda item: len(item[0]), reverse=True):
        if _category_alias_matches(alias, key):
            return category
    return "general"


def route_sites(
    product: str | None,
    *,
    category: str | None = None,
    city: str | None = None,
    color: str | None = None,
    route_enabled: bool = True,
) -> list[str]:
    """Return provider names to scrape for this product."""
    if not route_enabled:
        return list(DEFAULT_SITES)

    resolved_category = category if category in CATEGORY_SITES else classify_product(product)
    sites = CATEGORY_SITES.get(resolved_category, CATEGORY_SITES["general"])
    registered = set(DEFAULT_SITES)
    routed = [name for name in sites if name in registered] or list(CATEGORY_SITES["general"])
    return prioritize_sites_for_query(
        routed,
        city=city,
        color=color,
        category=resolved_category,
    )
