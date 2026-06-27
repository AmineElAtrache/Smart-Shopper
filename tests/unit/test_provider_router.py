"""Provider router coverage: every scrape provider must be reachable for its category."""

from __future__ import annotations

import pytest

from agents.orchestrator.tools.provider_router import (
    CATEGORY_SITES,
    DEFAULT_SITES,
    classify_product,
    route_sites,
)
from agents.orchestrator.tools.task_router import build_product_query
from agents.webscraping.agent import SCRAPE_PROVIDERS, _providers_for_task
from shared.events.schemas import EntityType, ExtractedEntity, ProductQuery, ScrapeTaskAssigned

# One sample product per provider (aligned with scripts/audit_scrape_providers.py smoke queries).
PROVIDER_SAMPLE_PRODUCT: dict[str, str] = {
    "jumia": "phone",
    "avito": "phone",
    "electrosalam": "laptop",
    "mafiawaystore": "shirt",
    "moteur": "car",
    "mymarket": "milk",
    "ultrapc": "laptop",
    "electroplanet": "tv",
    "defacto": "shirt",
    "biougnach": "tv",
    "marjane": "milk",
    "decathlon": "shoes",
    "mubawab": "apartment",
    "ikea": "chair",
    "palmarosa": "perfume",
    "bringo": "milk",
    "planetsport": "shoes",
}

# Providers that must NOT appear for these products (cross-category noise).
MUST_NOT_ROUTE: dict[str, set[str]] = {
    "phone": {"mubawab", "decathlon", "palmarosa", "marjane", "bringo", "mymarket", "ikea"},
    "refrigerator": {"mubawab", "decathlon", "palmarosa", "marjane", "moteur", "defacto"},
    "apartment": {"jumia", "decathlon", "palmarosa", "electroplanet", "moteur"},
    "milk": {"mubawab", "electroplanet", "moteur", "ikea", "ultrapc"},
    "perfume": {"mubawab", "decathlon", "moteur", "electrosalam", "ikea"},
}


def _scraper_provider_names() -> list[str]:
    return [name for name, _provider in SCRAPE_PROVIDERS]


def test_router_registry_matches_scraper_registry() -> None:
    assert DEFAULT_SITES == _scraper_provider_names()
    assert len(DEFAULT_SITES) == 17


def test_every_provider_has_sample_product_mapping() -> None:
    assert set(PROVIDER_SAMPLE_PRODUCT) == set(DEFAULT_SITES)


def test_all_providers_appear_in_category_routing_tables() -> None:
    routed = {site for sites in CATEGORY_SITES.values() for site in sites}
    assert routed == set(DEFAULT_SITES)


def test_category_site_lists_only_use_registered_providers() -> None:
    registered = set(DEFAULT_SITES)
    for category, sites in CATEGORY_SITES.items():
        unknown = set(sites) - registered
        assert not unknown, f"category {category} references unknown providers: {unknown}"


def test_category_site_lists_have_no_duplicates() -> None:
    for category, sites in CATEGORY_SITES.items():
        assert len(sites) == len(set(sites)), f"duplicate providers in {category}"


def test_routed_sites_are_subset_of_registry_and_unique() -> None:
    for product in PROVIDER_SAMPLE_PRODUCT.values():
        sites = route_sites(product)
        assert sites
        assert len(sites) == len(set(sites))
        assert set(sites).issubset(set(DEFAULT_SITES))


def test_route_disabled_returns_all_seventeen_providers() -> None:
    sites = route_sites("phone", route_enabled=False)
    assert sites == DEFAULT_SITES
    assert len(sites) == 17


@pytest.mark.parametrize("provider_name", DEFAULT_SITES)
def test_each_provider_is_routed_for_its_sample_product(provider_name: str) -> None:
    product = PROVIDER_SAMPLE_PRODUCT[provider_name]
    sites = route_sites(product)
    assert provider_name in sites, (
        f"{provider_name} missing for product={product!r}; got {sites}"
    )


@pytest.mark.parametrize(
    ("product", "forbidden"),
    [
        ("phone", MUST_NOT_ROUTE["phone"]),
        ("refrigerator", MUST_NOT_ROUTE["refrigerator"]),
        ("apartment", MUST_NOT_ROUTE["apartment"]),
        ("milk", MUST_NOT_ROUTE["milk"]),
        ("perfume", MUST_NOT_ROUTE["perfume"]),
    ],
)
def test_routing_excludes_irrelevant_providers(product: str, forbidden: set[str]) -> None:
    sites = set(route_sites(product))
    overlap = sites & forbidden
    assert not overlap, f"product={product!r} incorrectly routed to {overlap}"


@pytest.mark.parametrize("provider_name", DEFAULT_SITES)
def test_scraper_task_includes_only_routed_providers(provider_name: str) -> None:
    product = PROVIDER_SAMPLE_PRODUCT[provider_name]
    routed = route_sites(product)
    task = ScrapeTaskAssigned(
        request_id=f"req_{provider_name}",
        user_id="u",
        channel="telegram",
        query=ProductQuery(product=product, sites=routed),
    )
    selected = [name for name, _ in _providers_for_task(task)]
    registry_order = [name for name in _scraper_provider_names() if name in routed]
    assert set(selected) == set(routed)
    assert selected == registry_order
    assert provider_name in selected


def test_build_product_query_attaches_routed_sites_for_smoke_products() -> None:
    for provider_name, product in PROVIDER_SAMPLE_PRODUCT.items():
        query = build_product_query(
            [ExtractedEntity(type=EntityType.PRODUCT, value=product, confidence=0.9)]
        )
        assert query.product == product
        assert provider_name in query.sites


def test_classify_product_covers_smoke_categories() -> None:
    expectations = {
        "phone": "phone",
        "laptop": "laptop",
        "tv": "appliance",
        "refrigerator": "appliance",
        "car": "car",
        "apartment": "real_estate",
        "shirt": "fashion",
        "shoes": "sports",
        "milk": "grocery",
        "perfume": "beauty",
        "chair": "furniture",
    }
    for product, category in expectations.items():
        assert classify_product(product) == category


def test_route_sites_phone_skips_real_estate_and_sports() -> None:
    sites = route_sites("phone")

    assert "jumia" in sites
    assert "avito" in sites
    assert "electroplanet" in sites
    assert "mubawab" not in sites
    assert "decathlon" not in sites
    assert "palmarosa" not in sites
    assert len(sites) <= 8


def test_route_sites_fridge_targets_appliance_providers() -> None:
    sites = route_sites("refrigerator")

    assert sites == [
        "electroplanet",
        "biougnach",
        "jumia",
        "avito",
        "electrosalam",
    ]


def test_route_sites_apartment_targets_mubawab() -> None:
    sites = route_sites("apartment")

    assert sites == ["mubawab", "avito"]


def test_build_product_query_uses_routed_sites() -> None:
    query = build_product_query(
        [ExtractedEntity(type=EntityType.PRODUCT, value="phone", confidence=0.9)]
    )

    assert query.product == "phone"
    assert "jumia" in query.sites
    assert "mubawab" not in query.sites


def test_scraper_filters_providers_by_explicit_task_sites() -> None:
    task = ScrapeTaskAssigned(
        request_id="req_route",
        user_id="u",
        channel="telegram",
        query=ProductQuery(product="phone", sites=["jumia", "avito", "electroplanet"]),
    )

    providers = _providers_for_task(task)

    assert [name for name, _ in providers] == ["jumia", "avito", "electroplanet"]

def test_routes_air_fryer_as_appliance() -> None:
    assert classify_product("air fryer") == "appliance"
    assert classify_product("airfryer") == "appliance"
    assert route_sites("air fryer") == ["electroplanet", "biougnach", "jumia", "avito", "electrosalam"]
