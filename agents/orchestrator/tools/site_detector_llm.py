"""LLM fallback for ambiguous user-requested marketplace site detection."""

from __future__ import annotations

import json

import httpx

from agents.agent_generator.tools.llm_client import (
    OPENAI_COMPATIBLE_PROVIDERS,
    PROVIDER_DEFAULT_BASE_URLS,
)
from agents.orchestrator.tools.provider_router import DEFAULT_SITES
from agents.orchestrator.tools.provider_router_llm import JSON_FENCE_RE
from agents.orchestrator.tools.site_registry import validate_site_names
from shared.config import Settings

SYSTEM_PROMPT = f"""You extract marketplace website names explicitly requested by Moroccan shoppers.

Allowed sites only (use these exact ids):
{", ".join(DEFAULT_SITES)}

Reply with JSON only:
{{"sites":["jumia","avito"],"explicit":true}}

Rules:
- Return an empty list when the user did NOT ask for specific websites: {{"sites":[],"explicit":false}}
- Darija/French/English are valid ("mn jumia", "sur avito", "gir electroplanet")
- Map paraphrases to the closest allowed site id when clearly implied
- Do NOT invent sites outside the allowed list
- "explicit" is true only when the user clearly wants those specific marketplaces
- Ignore city/product/brand names unless they are also site names
"""


def build_site_detection_prompt(
    user_text: str,
    *,
    product: str | None = None,
    brand: str | None = None,
    city: str | None = None,
) -> str:
    hints = []
    if product:
        hints.append(f"product={product}")
    if brand:
        hints.append(f"brand={brand}")
    if city:
        hints.append(f"city={city}")
    return (
        f"User message:\n{user_text.strip()}\n\n"
        f"Known entities:\n" + ("\n".join(hints) if hints else "(none)")
    )


def parse_site_detection_response(text: str) -> tuple[list[str], bool]:
    cleaned = JSON_FENCE_RE.sub("", text.strip()).strip()
    if not cleaned:
        return [], False
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        return [], False
    if not isinstance(payload, dict):
        return [], False
    raw_sites = payload.get("sites") or []
    if not isinstance(raw_sites, list):
        return [], False
    sites = validate_site_names([str(site) for site in raw_sites])
    explicit = bool(payload.get("explicit")) and bool(sites)
    return sites, explicit


class SiteDetectorLlmClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def llm_enabled(self) -> bool:
        if not self._settings.scrape_user_sites_llm:
            return False
        provider = self._settings.llm_provider.lower().strip()
        api_key = (self._settings.llm_api_key or "").strip()
        return provider != "template" and bool(api_key)

    async def detect_sites(
        self,
        user_text: str,
        *,
        product: str | None = None,
        brand: str | None = None,
        city: str | None = None,
    ) -> tuple[list[str], bool]:
        if not self.llm_enabled():
            return [], False

        provider = self._settings.llm_provider.lower().strip()
        user_prompt = build_site_detection_prompt(
            user_text,
            product=product,
            brand=brand,
            city=city,
        )
        try:
            if provider in OPENAI_COMPATIBLE_PROVIDERS:
                raw = await self._call_openai_compatible(provider, user_prompt)
            elif provider == "gemini":
                raw = await self._call_gemini(provider, user_prompt)
            else:
                return [], False
        except Exception as exc:
            print(f"[orchestrator] site detection LLM failed: {exc}")
            return [], False

        return parse_site_detection_response(raw)

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
                    "max_tokens": 80,
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
