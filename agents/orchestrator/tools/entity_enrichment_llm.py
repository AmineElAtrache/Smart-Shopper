"""LLM-backed enrichment for missing city/color entities."""

from __future__ import annotations

import json

import httpx

from agents.agent_generator.tools.llm_client import (
    OPENAI_COMPATIBLE_PROVIDERS,
    PROVIDER_DEFAULT_BASE_URLS,
)
from agents.orchestrator.tools.provider_router_llm import JSON_FENCE_RE
from models.ner.product_vocabulary import city_aliases, normalize_key
from shared.config import Settings
from shared.events.schemas import EntityType, ExtractedEntity

COLOR_CANONICAL: dict[str, str] = {
    "black": "black",
    "noir": "black",
    "k7al": "black",
    "k7la": "black",
    "kehla": "black",
    "kahla": "black",
    "white": "white",
    "blanc": "white",
    "biad": "white",
    "byad": "white",
    "blue": "blue",
    "bleu": "blue",
    "red": "red",
    "rouge": "red",
    "green": "green",
    "vert": "green",
    "gray": "gray",
    "grey": "gray",
    "gris": "gray",
    "gold": "gold",
    "or": "gold",
    "silver": "silver",
    "argent": "silver",
    "brown": "brown",
    "marron": "brown",
}

SYSTEM_PROMPT = """You extract missing shopping query attributes for Moroccan users.

Reply with JSON only:
{"city":"rabat","color":"black"}

Rules:
- Use null for unknown fields: {"city":null,"color":null}
- city must be a Moroccan city canonical name in English (rabat, casablanca, fes, marrakech, tanger, agadir, ...)
- color must be one of: black, white, blue, red, green, gray, gold, silver, brown
- Darija/French/English input is valid (casa -> casablanca, kehla -> black, noir -> black)
- Do NOT invent city/color if the user did not imply them
- "f" before a city name is a preposition, not a city
"""


def build_enrichment_user_prompt(
    user_text: str,
    *,
    product: str | None = None,
    brand: str | None = None,
    city: str | None = None,
    color: str | None = None,
    budget: float | None = None,
) -> str:
    missing = []
    if not city:
        missing.append("city")
    if not color:
        missing.append("color")
    hints = []
    if product:
        hints.append(f"product={product}")
    if brand:
        hints.append(f"brand={brand}")
    if city:
        hints.append(f"city={city}")
    if color:
        hints.append(f"color={color}")
    if budget is not None:
        hints.append(f"budget={budget:g} MAD")
    return (
        f"User message:\n{user_text.strip()}\n\n"
        f"Fill only missing fields: {', '.join(missing) or 'none'}\n"
        f"Known entities:\n" + ("\n".join(hints) if hints else "(none)")
    )


def parse_enrichment_response(text: str) -> dict[str, str | None]:
    cleaned = JSON_FENCE_RE.sub("", text.strip()).strip()
    if not cleaned:
        return {}
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        "city": _normalize_city(payload.get("city")),
        "color": _normalize_color(payload.get("color")),
    }


def _normalize_city(value: object) -> str | None:
    if value is None:
        return None
    key = normalize_key(str(value))
    if not key:
        return None
    aliases = city_aliases()
    if key in aliases:
        return aliases[key]
    if key in aliases.values():
        return key
    return None


def _normalize_color(value: object) -> str | None:
    if value is None:
        return None
    key = normalize_key(str(value))
    if not key:
        return None
    return COLOR_CANONICAL.get(key, key if key in set(COLOR_CANONICAL.values()) else None)


class EntityEnrichmentLlmClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def enrichment_enabled(self) -> bool:
        if not self._settings.scrape_enrich_entities_llm:
            return False
        provider = self._settings.llm_provider.lower().strip()
        api_key = (self._settings.llm_api_key or "").strip()
        return provider != "template" and bool(api_key)

    async def enrich(
        self,
        user_text: str,
        *,
        product: str | None = None,
        brand: str | None = None,
        city: str | None = None,
        color: str | None = None,
        budget: float | None = None,
    ) -> dict[str, str]:
        if not self.enrichment_enabled():
            return {}
        if city and color:
            return {}

        provider = self._settings.llm_provider.lower().strip()
        user_prompt = build_enrichment_user_prompt(
            user_text,
            product=product,
            brand=brand,
            city=city,
            color=color,
            budget=budget,
        )
        try:
            if provider in OPENAI_COMPATIBLE_PROVIDERS:
                raw = await self._call_openai_compatible(provider, user_prompt)
            elif provider == "gemini":
                raw = await self._call_gemini(provider, user_prompt)
            else:
                return {}
        except Exception as exc:
            print(f"[orchestrator] entity enrichment LLM failed: {exc}")
            return {}

        parsed = parse_enrichment_response(raw)
        enriched: dict[str, str] = {}
        if not city and parsed.get("city"):
            enriched["city"] = parsed["city"]
        if not color and parsed.get("color"):
            enriched["color"] = parsed["color"]
        return enriched

    async def _call_openai_compatible(self, provider: str, user_prompt: str) -> str:
        async with httpx.AsyncClient(timeout=self._settings.llm_timeout_seconds) as client:
            response = await client.post(
                f"{self._base_url(provider).rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {self._settings.llm_api_key}"},
                json={
                    "model": self._settings.llm_model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.0,
                    "max_tokens": 60,
                },
            )
            response.raise_for_status()
            data = response.json()
            return str(data["choices"][0]["message"]["content"]).strip()

    async def _call_gemini(self, provider: str, user_prompt: str) -> str:
        prompt = f"{SYSTEM_PROMPT}\n\n{user_prompt}"
        async with httpx.AsyncClient(timeout=self._settings.llm_timeout_seconds) as client:
            response = await client.post(
                f"{self._base_url(provider).rstrip('/')}/models/{self._settings.llm_model}:generateContent",
                params={"key": self._settings.llm_api_key},
                json={"contents": [{"parts": [{"text": prompt}]}]},
            )
            response.raise_for_status()
            data = response.json()
            candidates = data.get("candidates") or []
            parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
            return str(parts[0].get("text", "")).strip()

    def _base_url(self, provider: str) -> str:
        configured = self._settings.llm_http_base_url.strip()
        if configured and configured != "http://localhost:8081":
            return configured
        return PROVIDER_DEFAULT_BASE_URLS.get(provider, configured)


def merge_enriched_entities(
    entities: list[ExtractedEntity],
    enriched: dict[str, str],
) -> list[ExtractedEntity]:
    if not enriched:
        return entities

    merged = list(entities)
    existing_types = {entity.type for entity in merged}
    if EntityType.CITY not in existing_types and enriched.get("city"):
        merged.append(
            ExtractedEntity(
                type=EntityType.CITY,
                value=enriched["city"],
                confidence=0.82,
                attributes={"source": "entity_enrichment_llm"},
            )
        )
    if EntityType.COLOR not in existing_types and enriched.get("color"):
        merged.append(
            ExtractedEntity(
                type=EntityType.COLOR,
                value=enriched["color"],
                confidence=0.82,
                attributes={"source": "entity_enrichment_llm"},
            )
        )
    return merged
