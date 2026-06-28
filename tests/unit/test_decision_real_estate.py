"""Decision filtering for real-estate queries with city aliases."""

from __future__ import annotations

from agents.decision.tools.scoring_engine import filter_relevant_products, rank_products
from shared.events.schemas import Availability, ProductQuery, RawProduct
from shared.query_matching import city_terms, resolve_city_key


def _listing(title: str, url: str, *, source: str = "mubawab", price: float = 950_000) -> RawProduct:
    return RawProduct(
        title=title,
        price=price,
        currency="MAD",
        source=source,
        url=url,
        availability=Availability.IN_STOCK,
        user_id="u1",
        query=ProductQuery(product="apartment"),
    )


def test_resolve_city_key_maps_casa_to_casablanca() -> None:
    assert resolve_city_key("casa") == "casablanca"
    assert "casablanca" in city_terms("casa")
    assert "casa" in city_terms("casa")


def test_filter_keeps_french_appartement_titles_for_apartment_query() -> None:
    query = ProductQuery(product="apartment", city="casablanca", budget=800_000, sites=["mubawab", "avito"])
    products = [
        _listing(
            "Appartement a vendre a Casablanca",
            "https://www.mubawab.ma/fr/a/123456/appartement-a-vendre-casablanca",
        ),
        _listing(
            "Villa a vendre Rabat",
            "https://www.mubawab.ma/fr/a/345678/villa-a-vendre-rabat",
            price=3_500_000,
        ),
    ]

    filtered = filter_relevant_products(products, query)

    assert len(filtered) == 1
    assert "appartement" in filtered[0].title.lower()


def test_rank_products_returns_apartment_listings_for_casa_query() -> None:
    query = ProductQuery(product="apartment", city="casa", budget=8_000_000, sites=["avito", "mubawab"])
    products = [
        _listing(
            "Appartement 2 chambres Maarif Casablanca",
            "https://www.avito.ma/fr/casablanca/appartements/appartement-123",
            source="avito",
            price=1_150_000,
        ),
        _listing(
            "Villa a vendre Rabat",
            "https://www.avito.ma/fr/rabat/villas/villa-456",
            source="avito",
            price=3_500_000,
        ),
    ]

    ranked = rank_products(products, query)

    assert len(ranked) == 1
    assert "appartement" in ranked[0].title.lower()
