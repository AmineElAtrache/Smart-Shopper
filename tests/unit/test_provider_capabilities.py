"""Tests for provider capability map and city/color-aware routing."""

from __future__ import annotations

from agents.orchestrator.tools.provider_capabilities import (
    capabilities_for,
    color_filter_relevant,
    city_filter_relevant,
    prioritize_sites_for_query,
)
from agents.orchestrator.tools.provider_router import route_sites


def test_avito_prioritized_when_city_set_for_phone() -> None:
    without_city = route_sites("phone", category="phone")
    with_city = route_sites("phone", category="phone", city="rabat")

    assert with_city[0] == "avito"
    assert set(with_city) == set(without_city)


def test_mubawab_prioritized_for_real_estate_with_city() -> None:
    sites = route_sites("apartment", category="real_estate", city="casablanca")

    assert sites[0] in {"mubawab", "avito"}
    assert "mubawab" in sites


def test_prioritize_sites_preserves_all_sites() -> None:
    base = ["jumia", "avito", "electroplanet"]
    reordered = prioritize_sites_for_query(base, city="rabat", category="phone")

    assert set(reordered) == set(base)
    assert len(reordered) == len(base)


def test_city_filter_relevant_for_furniture() -> None:
    assert city_filter_relevant("furniture", "rabat") is True
    assert city_filter_relevant("grocery", "rabat") is False


def test_color_filter_relevant_for_fashion() -> None:
    assert color_filter_relevant("fashion", "black") is True
    assert color_filter_relevant("grocery", "black") is False


def test_jumia_supports_city_in_search_text_only() -> None:
    caps = capabilities_for("jumia")

    assert caps.city_in_search_text is True
    assert caps.city_in_url is False
    assert caps.supports_city is False
