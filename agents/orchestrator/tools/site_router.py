"""Resolve final scrape sites from user intent, category routing, and policies."""

from __future__ import annotations

from agents.orchestrator.tools.provider_capabilities import prioritize_sites_for_query
from agents.orchestrator.tools.provider_router import route_sites
from agents.orchestrator.tools.site_detector import (
    SiteDetectionResult,
    SiteDetectionSource,
    detect_sites_hybrid,
)
from agents.orchestrator.tools.site_detector_llm import SiteDetectorLlmClient
from agents.orchestrator.tools.site_registry import validate_site_names
from shared.config import Settings
from shared.events.schemas import EntityType, ExtractedEntity


class SiteRouter:
    def __init__(
        self,
        settings: Settings,
        llm_client: SiteDetectorLlmClient | None = None,
    ) -> None:
        self._settings = settings
        self._llm = llm_client or SiteDetectorLlmClient(settings)

    async def resolve_sites(
        self,
        user_text: str,
        entities: list[ExtractedEntity],
        *,
        product: str | None = None,
        category: str | None = None,
        city: str | None = None,
        color: str | None = None,
        route_enabled: bool = True,
    ) -> list[str]:
        routed = route_sites(
            product,
            category=category,
            city=city,
            color=color,
            route_enabled=route_enabled,
        )
        if not self._settings.scrape_user_sites_enabled:
            return routed

        detection = detect_sites_hybrid(user_text, entities, product=product)
        user_sites = list(detection.sites)

        if detection.ambiguous and self._llm.llm_enabled():
            llm_sites, _llm_explicit = await self._llm.detect_sites(
                user_text,
                product=product,
                brand=_entity_value(entities, EntityType.BRAND),
                city=city,
            )
            if llm_sites:
                user_sites = validate_site_names([*user_sites, *llm_sites])
                detection = SiteDetectionResult(
                    sites=tuple(user_sites),
                    explicit=True,
                    source=SiteDetectionSource.LLM,
                    confidence=0.88,
                )

        if detection.excluded:
            routed = [site for site in routed if site not in detection.excluded]

        if not user_sites:
            return routed

        user_sites = validate_site_names(user_sites)
        if not user_sites:
            return routed

        if self._settings.scrape_user_sites_strict:
            return prioritize_sites_for_query(
                user_sites,
                city=city,
                color=color,
                category=category,
            )

        merged: list[str] = []
        seen: set[str] = set()
        for site in [*user_sites, *routed]:
            if site not in seen:
                merged.append(site)
                seen.add(site)
        return merged


def _entity_value(entities: list[ExtractedEntity], entity_type: EntityType) -> str | None:
    for entity in entities:
        if entity.type == entity_type:
            return entity.value
    return None
