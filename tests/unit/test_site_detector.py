"""Tests for hybrid user-requested site detection and routing."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from agents.orchestrator.tools.site_detector import (
    detect_sites_from_rules,
    detect_sites_hybrid,
)
from agents.orchestrator.tools.site_detector_llm import SiteDetectorLlmClient, parse_site_detection_response
from agents.orchestrator.tools.site_registry import canonical_site_name, validate_site_names
from agents.orchestrator.tools.site_router import SiteRouter
from agents.orchestrator.tools.task_router import build_product_query
from shared.config import Settings
from shared.events.schemas import EntityType, ExtractedEntity


def test_canonical_site_name_maps_aliases() -> None:
    assert canonical_site_name("jumia") == "jumia"
    assert canonical_site_name("Jumia.ma") == "jumia"
    assert canonical_site_name("site_jumia") == "jumia"
    assert canonical_site_name("amazon") is None


def test_validate_site_names_preserves_order_and_dedupes() -> None:
    assert validate_site_names(["jumia", "avito", "jumia", "unknown"]) == ["jumia", "avito"]


def test_detect_sites_from_rules_single_provider() -> None:
    result = detect_sites_from_rules("bghit phone mn jumia b 3000dh", product="phone")

    assert result.sites == ("jumia",)
    assert result.explicit is True


def test_detect_sites_from_rules_multiple_providers() -> None:
    result = detect_sites_from_rules("phone jumia w avito", product="phone")

    assert result.sites == ("jumia", "avito")


def test_detect_sites_from_rules_excludes_provider() -> None:
    result = detect_sites_from_rules("phone bla avito mn jumia", product="phone")

    assert result.sites == ("jumia",)
    assert result.excluded == ("avito",)


def test_detect_sites_from_rules_url() -> None:
    result = detect_sites_from_rules(
        "bghit phone https://www.jumia.ma/catalog/?q=phone",
        product="phone",
    )

    assert result.sites == ("jumia",)


def test_detect_sites_from_entities_intent_site_prefix() -> None:
    entities = [
        ExtractedEntity(type=EntityType.INTENT, value="site_avito", confidence=0.9),
    ]
    result = detect_sites_hybrid("phone f avito", entities, product="phone")

    assert "avito" in result.sites


def test_parse_site_detection_response() -> None:
    sites, explicit = parse_site_detection_response('{"sites":["jumia","avito"],"explicit":true}')

    assert sites == ["jumia", "avito"]
    assert explicit is True


@pytest.mark.asyncio
async def test_site_router_strict_override() -> None:
    settings = Settings(
        _env_file=None,
        scrape_user_sites_enabled=True,
        scrape_user_sites_strict=True,
        scrape_user_sites_llm=False,
    )
    router = SiteRouter(settings)
    sites = await router.resolve_sites(
        "bghit phone mn jumia b 3000dh",
        [ExtractedEntity(type=EntityType.PRODUCT, value="phone", confidence=0.9)],
        product="phone",
        category="phone",
    )

    assert sites == ["jumia"]


@pytest.mark.asyncio
async def test_site_router_falls_back_to_category_routing() -> None:
    settings = Settings(_env_file=None, scrape_user_sites_enabled=True, scrape_user_sites_strict=True)
    router = SiteRouter(settings)
    sites = await router.resolve_sites(
        "bghit phone b 3000dh",
        [ExtractedEntity(type=EntityType.PRODUCT, value="phone", confidence=0.9)],
        product="phone",
        category="phone",
    )

    assert "jumia" in sites
    assert "avito" in sites
    assert len(sites) > 1


@pytest.mark.asyncio
async def test_site_router_uses_llm_when_ambiguous() -> None:
    settings = Settings(_env_file=None, scrape_user_sites_enabled=True, scrape_user_sites_strict=True)
    llm = SiteDetectorLlmClient(settings)
    llm.llm_enabled = lambda: True  # type: ignore[method-assign]
    llm.detect_sites = AsyncMock(return_value=(["electroplanet"], True))
    router = SiteRouter(settings, llm_client=llm)

    sites = await router.resolve_sites(
        "bghit tv mn site dyal electronics",
        [ExtractedEntity(type=EntityType.PRODUCT, value="tv", confidence=0.9)],
        product="tv",
        category="appliance",
    )

    assert sites == ["electroplanet"]
    llm.detect_sites.assert_awaited_once()


def test_build_product_query_accepts_explicit_sites() -> None:
    query = build_product_query(
        [ExtractedEntity(type=EntityType.PRODUCT, value="phone", confidence=0.9)],
        category="phone",
        sites=["jumia"],
    )

    assert query.sites == ["jumia"]
