"""Shared city/color matching helpers."""

from __future__ import annotations

from shared.events.schemas import Availability, ProductQuery, RawProduct
from shared.query_matching import matches_city_and_color, matches_color_in_text


def test_matches_color_accepts_darija_alias() -> None:
    query = ProductQuery(product="phone", color="black")

    assert matches_color_in_text("Samsung kehla", query) is True
    assert matches_color_in_text("Samsung blanc", query) is False


def test_matches_city_and_color_on_product_metadata() -> None:
    query = ProductQuery(product="phone", city="casablanca", color="black")
    product = RawProduct(
        title="Samsung Galaxy",
        price=2500,
        currency="MAD",
        source="avito",
        url="https://avito.ma/casa/item",
        availability=Availability.IN_STOCK,
        user_id="u1",
        query=query,
        metadata={"city": "Casablanca", "color": "noir"},
    )

    assert matches_city_and_color(product, query) is True
