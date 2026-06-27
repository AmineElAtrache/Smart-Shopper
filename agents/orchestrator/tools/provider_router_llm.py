"""LLM-backed product category routing for marketplace provider selection."""

from __future__ import annotations

import json
import re

import httpx

from agents.agent_generator.tools.llm_client import (
    OPENAI_COMPATIBLE_PROVIDERS,
    PROVIDER_DEFAULT_BASE_URLS,
)
from agents.orchestrator.tools.provider_router import (
    CATEGORY_SITES,
    ROUTING_CATEGORIES,
    classify_product,
)
from shared.config import Settings

JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)

SYSTEM_PROMPT = """You classify Moroccan shopping queries into exactly one marketplace category.

Allowed categories (pick one):
phone, laptop, appliance, car, real_estate, fashion, sports, grocery, beauty, furniture, general

Rules:
- Use the FULL user message, not only NER hints
- Darija, French, and English are all valid
- "table" / "tabla" (furniture) is NOT the same as "tablet" / "tablette" (electronics)
- Apartments and houses → real_estate; cars → car; food → grocery
- If unsure, use general

Reply with JSON only, no markdown or explanation:
{"category":"furniture"}
"""


def build_routing_user_prompt(
    user_text: str,
    *,
    product: str | None = None,
    brand: str | None = None,
    city: str | None = None,
    budget: float | None = None,
    currency: str = "MAD",
) -> str:
    hints: list[str] = []
    if product:
        hints.append(f"product={product}")
    if brand:
        hints.append(f"brand={brand}")
    if city:
        hints.append(f"city={city}")
    if budget is not None:
        hints.append(f"budget={budget:g} {currency}")

    hint_block = "\n".join(hints) if hints else "(no NER hints)"
    return (
        f"User message:\n{user_text.strip()}\n\n"
        f"NER hints:\n{hint_block}"
    )


def parse_category_response(text: str) -> str | None:
    cleaned = JSON_FENCE_RE.sub("", text.strip()).strip()
    if not cleaned:
        return None

    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        lowered = cleaned.lower()
        for category in ROUTING_CATEGORIES:
            if re.search(rf'["\']?category["\']?\s*[:=]\s*["\']?{category}["\']?', lowered):
                return category
        for category in ROUTING_CATEGORIES:
            if re.fullmatch(rf"{category}", lowered):
                return category
        return None

    category = str(payload.get("category") or "").strip().lower()
    if category in CATEGORY_SITES:
        return category
    return None


class ProviderRouterLlmClient:
    """Classify shopping queries with the project LLM; static router is the fallback."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def llm_routing_enabled(self) -> bool:
        if not self._settings.scrape_route_use_llm:
            return False
        provider = self._settings.llm_provider.lower().strip()
        api_key = (self._settings.llm_api_key or "").strip()
        return provider != "template" and bool(api_key)

    async def classify_category(
        self,
        user_text: str,
        *,
        product: str | None = None,
        brand: str | None = None,
        city: str | None = None,
        budget: float | None = None,
        currency: str = "MAD",
    ) -> str | None:
        if not self.llm_routing_enabled():
            return None

        provider = self._settings.llm_provider.lower().strip()
        user_prompt = build_routing_user_prompt(
            user_text,
            product=product,
            brand=brand,
            city=city,
            budget=budget,
            currency=currency,
        )

        try:
            if provider in OPENAI_COMPATIBLE_PROVIDERS:
                raw = await self._call_openai_compatible(provider, user_prompt)
            elif provider == "gemini":
                raw = await self._call_gemini(provider, user_prompt)
            else:
                print(f"[orchestrator] unsupported provider-router LLM provider {provider}")
                return None

            category = parse_category_response(raw)
            if category is None:
                print(f"[orchestrator] provider-router LLM returned invalid category: {raw!r}")
            return category
        except Exception as exc:
            print(f"[orchestrator] provider-router LLM failed, using static fallback: {exc}")
            return None

    def static_category(self, product: str | None) -> str:
        return classify_product(product)

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
                    "max_tokens": 40,
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
