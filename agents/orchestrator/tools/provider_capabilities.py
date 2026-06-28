"""Provider capability map for city/color-aware routing and scraping."""

from __future__ import annotations

from dataclasses import dataclass

# Categories where a user-supplied city is meaningful for result quality.
CITY_RELEVANT_CATEGORIES: frozenset[str] = frozenset(
    {"car", "real_estate", "furniture", "general", "phone", "laptop", "appliance", "fashion"}
)

# Categories where color filtering/search is meaningful.
COLOR_RELEVANT_CATEGORIES: frozenset[str] = frozenset(
    {"phone", "laptop", "fashion", "sports", "general", "appliance", "furniture"}
)


@dataclass(frozen=True)
class ProviderCapabilities:
    supports_city: bool = False
    supports_color: bool = True
    city_in_url: bool = False
    city_in_search_text: bool = False
    prioritize_when_city_set: bool = False


PROVIDER_CAPABILITIES: dict[str, ProviderCapabilities] = {
    "avito": ProviderCapabilities(
        supports_city=True,
        supports_color=True,
        city_in_url=True,
        city_in_search_text=True,
        prioritize_when_city_set=True,
    ),
    "mubawab": ProviderCapabilities(
        supports_city=True,
        supports_color=False,
        city_in_url=True,
        prioritize_when_city_set=True,
    ),
    "moteur": ProviderCapabilities(
        supports_city=True,
        supports_color=False,
        prioritize_when_city_set=True,
    ),
    "jumia": ProviderCapabilities(
        supports_city=False,
        supports_color=True,
        city_in_search_text=True,
    ),
    "ikea": ProviderCapabilities(supports_city=False, supports_color=True),
    "electroplanet": ProviderCapabilities(supports_city=False, supports_color=True),
    "electrosalam": ProviderCapabilities(supports_city=False, supports_color=True),
    "ultrapc": ProviderCapabilities(supports_city=False, supports_color=True),
    "biougnach": ProviderCapabilities(supports_city=False, supports_color=True),
    "defacto": ProviderCapabilities(supports_city=False, supports_color=True),
    "decathlon": ProviderCapabilities(supports_city=False, supports_color=True),
    "planetsport": ProviderCapabilities(supports_city=False, supports_color=True),
    "palmarosa": ProviderCapabilities(supports_city=False, supports_color=True),
    "marjane": ProviderCapabilities(supports_city=False, supports_color=True),
    "mymarket": ProviderCapabilities(supports_city=False, supports_color=True),
    "bringo": ProviderCapabilities(supports_city=False, supports_color=True),
    "mafiawaystore": ProviderCapabilities(supports_city=False, supports_color=True),
}


def capabilities_for(provider: str) -> ProviderCapabilities:
    return PROVIDER_CAPABILITIES.get(provider.lower(), ProviderCapabilities())


def city_filter_relevant(category: str | None, city: str | None) -> bool:
    return bool(city) and (not category or category in CITY_RELEVANT_CATEGORIES)


def color_filter_relevant(category: str | None, color: str | None) -> bool:
    return bool(color) and (not category or category in COLOR_RELEVANT_CATEGORIES)


def sites_support_city_filter(sites: list[str]) -> bool:
    return any(capabilities_for(site).supports_city for site in sites)


def prioritize_sites_for_query(
    sites: list[str],
    *,
    city: str | None = None,
    color: str | None = None,
    category: str | None = None,
) -> list[str]:
    """Reorder routed sites using provider capabilities without dropping registered sites."""
    if not sites:
        return sites

    scored: list[tuple[int, int, str]] = []
    for index, site in enumerate(sites):
        caps = capabilities_for(site)
        score = 0
        if city and city_filter_relevant(category, city):
            if caps.prioritize_when_city_set:
                score += 20
            if caps.supports_city:
                score += 10
            if caps.city_in_url:
                score += 5
        if color and color_filter_relevant(category, color) and caps.supports_color:
            score += 3
        scored.append((score, index, site))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [site for _, _, site in scored]
