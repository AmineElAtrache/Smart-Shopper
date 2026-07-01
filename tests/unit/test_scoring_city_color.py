"""Decision scoring filters for city and color."""

from __future__ import annotations

from agents.decision.tools.scoring_engine import filter_relevant_products
from shared.events.schemas import Availability, ProductQuery, RawProduct


def _product(title: str, *, url: str = "https://example.test/item", source: str = "jumia") -> RawProduct:
    return RawProduct(
        title=title,
        price=2500,
        currency="MAD",
        source=source,
        url=url,
        availability=Availability.IN_STOCK,
        user_id="u1",
        query=ProductQuery(product="phone"),
    )


def test_filter_keeps_city_and_color_matches() -> None:
    query = ProductQuery(product="phone", city="rabat", color="black")
    products = [
        _product("Samsung Galaxy noir Rabat", source="avito"),
        _product("Samsung Galaxy white Casablanca", source="avito"),
    ]

    filtered = filter_relevant_products(products, query)

    assert len(filtered) == 1
    assert "noir" in filtered[0].title.lower()


def test_filter_soft_color_fallback_when_no_color_match(monkeypatch) -> None:
    monkeypatch.setenv("SCRAPE_SOFT_COLOR_FALLBACK", "true")
    query = ProductQuery(product="phone", city="rabat", color="black")
    products = [
        _product("Samsung Galaxy Rabat", source="avito"),
        _product("Samsung Galaxy Casablanca", source="avito"),
    ]

    filtered = filter_relevant_products(products, query)

    assert len(filtered) == 1
    assert "rabat" in filtered[0].title.lower()


def test_filter_skips_city_on_non_city_capable_sources() -> None:
    query = ProductQuery(product="phone", city="rabat", sites=["jumia"])
    products = [
        _product("Samsung Galaxy A15", source="jumia"),
    ]

    filtered = filter_relevant_products(products, query)

    assert len(filtered) == 1


def test_filter_strict_color_when_soft_fallback_disabled(monkeypatch) -> None:
    monkeypatch.setenv("SCRAPE_SOFT_COLOR_FALLBACK", "false")
    query = ProductQuery(product="phone", city="rabat", color="black")
    products = [
        _product("Samsung Galaxy noir Rabat", source="avito"),
        _product("Samsung Galaxy Rabat", source="avito"),
    ]

    filtered = filter_relevant_products(products, query)

    assert len(filtered) == 1
    assert "noir" in filtered[0].title.lower()
